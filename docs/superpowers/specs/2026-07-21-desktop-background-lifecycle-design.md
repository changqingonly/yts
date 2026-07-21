# Desktop Background Lifecycle Design

## Goal

Make the macOS desktop lifecycle match normal media application behavior:

- Closing the main window with the red close button closes the GUI only. Music playback,
  generation tasks, the Python sidecar, and the inference gateway keep running.
- Choosing `Quit` from either the application menu or the menu bar status item stops every
  process owned by that LeTu instance and then exits the application.
- If the Tauri process is terminated without running cleanup, including `SIGKILL`, the Python
  sidecar and inference gateway detect loss of their lifecycle connection, stop their owned
  work, and exit within three seconds.

The application must never identify owned processes by executable name. Docker Desktop,
development `servctl` processes, and processes owned by another application instance are out
of scope and must not be stopped.

## Current Failure

The current Tauri shell stores only the direct `CommandChild` for `yts-sidecar` and
`infer-gateway`. On `RunEvent::Exit`, it calls `kill()` and discards every result. It then runs
`pkill -9 -f` against the packaged sidecar path and discards that result as well.

This has four control-flow defects:

1. Closing a window and exiting the application are not modeled as different transitions.
2. `SIGKILL` prevents `RunEvent::Exit` from running, so the current cleanup path cannot execute.
3. The gateway launches llama, image, and music commands through `sh -c`; killing the stored
   shell or gateway PID does not prove that the complete producer process tree stopped.
4. Cleanup failures are silent, so the application can report success while ports or model
   processes remain alive.

The installed application logs show historical gateway termination, and the currently running
Python service on port 8000 belongs to development `servctl`, not the packaged local sidecar.
That evidence does not remove the defects above; it only means no packaged local process was
alive at inspection time.

## Chosen Architecture

The Tauri process remains the background application controller after the main window closes.
No LaunchAgent is installed, and LeTu does not start at login as part of this change.

```text
main window ----> Tauri application controller <---- menu bar status item
                           |
                           +---- lifecycle IPC ---- Python sidecar
                           |
                           +---- lifecycle IPC ---- inference gateway
                                                       |
                                                       +---- llama process group
                                                       +---- image process groups
                                                       +---- music process groups
```

The Tauri controller owns only the two packaged top-level children. The inference gateway owns
every native producer it starts. Ownership is explicit and instance-scoped.

## Window And Application State

The application has three explicit states:

- `Running`: the controller and background services may run; the main window may be visible or
  hidden.
- `Stopping`: no new local work is accepted; one shutdown operation is in progress.
- `Stopped`: all owned processes have been verified absent and the Tauri event loop may exit.

The main window close event is intercepted only while `Running`. It hides the window and keeps
the controller alive. Activating the Dock icon or choosing `Open LeTu` from the status item
shows and focuses the existing window.

Both visible `Quit` actions call the same transition from `Running` to `Stopping`. Repeated quit
requests observe the existing shutdown operation rather than starting a second one. The window
close handler does not hide the window once `Stopping` has begun.

## Lifecycle IPC

At application startup, Tauri creates an instance-specific Unix domain socket below the app
runtime directory and generates a cryptographically random instance token. The socket path and
token are passed to each packaged child through environment variables.

Each child must connect and authenticate with its component name and instance token before it
reports startup success. Failure to establish the lifecycle channel is a startup failure; the
component must not continue as an unmanaged service.

The connection is bidirectional:

- Tauri sends a structured `shutdown` command during a normal application quit.
- The component responds with `stopped` only after its own server and owned descendants have
  stopped.
- EOF without a `shutdown` command means the Tauri process disappeared unexpectedly. The
  component immediately enters the same shutdown routine.

The protocol uses framed JSON messages with a schema version. Malformed messages, token
mismatches, duplicate component registrations, and unexpected connection closure during normal
shutdown are explicit errors in the desktop log.

The Unix socket is the lifecycle signal; parent-PID polling and process-name scanning are not
additional fallback mechanisms.

## Owned Process Groups

Every command started by the inference gateway is placed in a new Unix process group before
execution. This includes the persistent llama server and every image or music producer launched
through `sh -c`.

The gateway maintains a registry containing the producer kind, child PID, process-group ID, and
request identifier. A producer is removed only after `wait()` confirms its termination. Request
cancellation and gateway shutdown operate on the registered process group, not only the shell
PID.

Gateway shutdown performs these steps in order:

1. Stop accepting HTTP and WebSocket work.
2. Cancel active requests.
3. Send `SIGTERM` to all registered producer process groups.
4. Reap terminated children.
5. If a group remains alive at the escalation deadline, record an error and send `SIGKILL` to
   that exact owned process group.
6. Verify that the registry is empty and gateway listener ports are released.
7. Send the lifecycle `stopped` acknowledgement and exit.

The Python sidecar stops its Uvicorn server through its normal shutdown API, verifies that port
8765 is released, acknowledges `stopped`, and exits. This also lets the PyInstaller worker exit
through its normal control flow instead of relying on a package-path `pkill`.

## Three-Second Deadline

The externally observable requirement is that all owned processes and local listener ports are
gone within three seconds of an application quit request or lifecycle EOF.

The shutdown coordinator uses one monotonic deadline shared by every component. Work proceeds
concurrently where dependencies allow; each layer receives the remaining time rather than a new
three-second allowance. The producer escalation point is early enough to leave time for process
reaping and final verification.

If normal quit reaches the deadline without verification, Tauri writes a fatal shutdown record
containing component, PID, process-group ID, port, elapsed time, and operating-system error. It
then terminates only the exact remaining owned process groups and reports that escalation in the
log. Errors are never converted to a successful `stopped` acknowledgement.

During `SIGKILL` of Tauri, the children own the deadline and diagnostics. Each writes to its own
existing desktop log stream before exiting. A test that observes any owned PID or port after the
deadline fails.

## Menu Bar Behavior

The application adds a macOS menu bar status item with these commands:

- `Open LeTu`: show and focus the main window.
- `Quit`: run the shared application shutdown transition.

The application menu `Quit LeTu` invokes the identical command. Neither action merely hides the
window. The red window button never invokes application shutdown.

## Logging And Error Exposure

The existing desktop log writer must return errors to its caller instead of silently returning.
Tauri passes the resolved desktop log path to both children. The children append their own
lifecycle records directly to that file, so diagnostics remain available after `SIGKILL` closes
the stdout and stderr pipes owned by Tauri. Shutdown records are structured and include an
instance identifier so packaged lifecycle tests can correlate one launch with its children.

Expected lifecycle transitions are informational. Failed authentication, failed signals,
deadline escalation, unreaped children, and occupied owned ports are errors. A component that
cannot prove it is managed fails startup rather than running without supervision.

## Testing

Focused unit tests cover:

- window close versus application quit state transitions;
- idempotent quit handling;
- lifecycle authentication and framed-message validation;
- EOF entering shutdown without a Tauri callback;
- one shared monotonic deadline;
- producer registry insertion, reaping, and exact process-group signaling;
- propagation of shutdown and logging errors.

macOS integration tests launch disposable nested shell processes and verify that terminating the
registered group removes both shell and descendant. They also run the sidecar and gateway with a
test lifecycle socket, close the socket, and assert that their PIDs and ports disappear within
three seconds.

The packaged acceptance test exercises the real `.app`:

1. Start LeTu and local services, close the main window, and verify playback/services remain.
2. Reopen the window from the Dock and from the status item.
3. Quit from the application menu and verify all recorded PIDs plus ports 8765/8799 disappear
   within three seconds.
4. Repeat using the status-item `Quit` command.
5. Start active llama, image, and music producers, send `SIGKILL` to the Tauri PID, and verify all
   instance-owned PIDs, process groups, and ports disappear within three seconds.
6. Keep a development `servctl` process running throughout and verify it is untouched.

## Non-Goals

- Running LeTu services after the application process has exited normally.
- Login startup or an independently persistent LaunchAgent.
- Cleaning stale processes by executable name, command substring, or port owner.
- Managing Docker Desktop or development services.
- Changing inference, playback, or generation business behavior beyond lifecycle cancellation.
