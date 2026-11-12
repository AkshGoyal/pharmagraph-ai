// Native macOS wrapper: no Terminal window or commands required.
import AppKit
import Foundation

final class PharmaGraphLauncher: NSObject, NSApplicationDelegate {
    let root = Bundle.main.bundleURL.deletingLastPathComponent()
    var window: NSWindow!
    let heading = NSTextField(labelWithString: "Starting PharmaGraph…")
    let detail = NSTextField(wrappingLabelWithString: "Starting the local database and workspace. Your browser will open after the database connection and saved data are checked. This can take a minute.")
    let progress = NSProgressIndicator()
    let openButton = NSButton(title: "Open PharmaGraph", target: nil, action: nil)
    var address: URL?

    func applicationDidFinishLaunching(_ notification: Notification) {
        buildWindow()
        let appMenu = NSMenu()
        let rootItem = NSMenuItem()
        let actions = NSMenu()
        let open = NSMenuItem(title: "Open PharmaGraph", action: #selector(openBrowser), keyEquivalent: "o")
        open.target = self
        actions.addItem(open)
        actions.addItem(.separator())
        actions.addItem(withTitle: "Quit PharmaGraph", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        rootItem.submenu = actions
        appMenu.addItem(rootItem)
        NSApp.mainMenu = appMenu
        NSApp.activate(ignoringOtherApps: true)

        let python = root.appendingPathComponent(".venv/bin/python")
        let script = root.appendingPathComponent("scripts/launch.py")
        guard FileManager.default.isExecutableFile(atPath: python.path),
              FileManager.default.fileExists(atPath: script.path) else {
            failed("Keep PharmaGraph.app in the project folder beside app.py and its .venv folder. The installed project environment is required.")
            return
        }
        DispatchQueue.global(qos: .userInitiated).async { [self] in
            let result = runHelper([])
            DispatchQueue.main.async { [self] in
                guard result.code == 0, let url = URL(string: result.output.trimmingCharacters(in: .whitespacesAndNewlines)),
                      url.host == "127.0.0.1", url.scheme == "http" else {
                    failed(result.error.isEmpty ? "The local workspace could not start. Try opening PharmaGraph again." : result.error)
                    return
                }
                address = url
                progress.stopAnimation(nil)
                progress.isHidden = true
                heading.stringValue = "PharmaGraph is ready"
                detail.stringValue = "Your local database and workspace are ready, including live batch investigations. Keep this launcher open while you use the project.\n\nQuit PharmaGraph to stop the web server and any database started by this launcher. Your saved database is retained."
                openButton.isEnabled = true
                openBrowser()
            }
        }
    }

    func buildWindow() {
        window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 500, height: 310),
                          styleMask: [.titled, .closable, .miniaturizable], backing: .buffered, defer: false)
        window.title = "PharmaGraph"
        window.isReleasedWhenClosed = false
        window.center()
        let content = window.contentView!
        let icon = NSImageView()
        icon.image = NSImage(systemSymbolName: "cross.case.fill", accessibilityDescription: "PharmaGraph")
        icon.contentTintColor = NSColor(calibratedRed: 0.03, green: 0.50, blue: 0.51, alpha: 1)
        heading.font = .systemFont(ofSize: 22, weight: .semibold)
        detail.font = .systemFont(ofSize: 13)
        detail.textColor = .secondaryLabelColor
        progress.style = .spinning
        progress.controlSize = .small
        progress.startAnimation(nil)
        openButton.target = self
        openButton.action = #selector(openBrowser)
        openButton.bezelStyle = .rounded
        openButton.keyEquivalent = "\r"
        openButton.isEnabled = false
        let quit = NSButton(title: "Quit PharmaGraph", target: NSApp, action: #selector(NSApplication.terminate(_:)))
        quit.bezelStyle = .rounded
        for view in [icon, heading, detail, progress, openButton, quit] {
            view.translatesAutoresizingMaskIntoConstraints = false
            content.addSubview(view)
        }
        NSLayoutConstraint.activate([
            icon.leadingAnchor.constraint(equalTo: content.leadingAnchor, constant: 30),
            icon.topAnchor.constraint(equalTo: content.topAnchor, constant: 30),
            icon.widthAnchor.constraint(equalToConstant: 38), icon.heightAnchor.constraint(equalToConstant: 38),
            heading.leadingAnchor.constraint(equalTo: icon.trailingAnchor, constant: 15),
            heading.centerYAnchor.constraint(equalTo: icon.centerYAnchor),
            detail.leadingAnchor.constraint(equalTo: content.leadingAnchor, constant: 30),
            detail.trailingAnchor.constraint(equalTo: content.trailingAnchor, constant: -30),
            detail.topAnchor.constraint(equalTo: icon.bottomAnchor, constant: 22),
            progress.leadingAnchor.constraint(equalTo: detail.leadingAnchor),
            progress.topAnchor.constraint(equalTo: detail.bottomAnchor, constant: 15),
            openButton.trailingAnchor.constraint(equalTo: content.trailingAnchor, constant: -30),
            openButton.bottomAnchor.constraint(equalTo: content.bottomAnchor, constant: -25),
            quit.trailingAnchor.constraint(equalTo: openButton.leadingAnchor, constant: -12),
            quit.centerYAnchor.constraint(equalTo: openButton.centerYAnchor),
        ])
        window.makeKeyAndOrderFront(nil)
    }

    func runHelper(_ arguments: [String]) -> (code: Int32, output: String, error: String) {
        let process = Process()
        process.executableURL = root.appendingPathComponent(".venv/bin/python")
        process.arguments = [root.appendingPathComponent("scripts/launch.py").path] + arguments
        process.currentDirectoryURL = root
        let output = Pipe()
        let errors = Pipe()
        process.standardOutput = output
        process.standardError = errors
        do {
            try process.run()
            // The helper's output is intentionally small; server logs go to a file.
            process.waitUntilExit()
            return (process.terminationStatus,
                    String(data: output.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? "",
                    String(data: errors.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? "")
        } catch {
            return (1, "", "The installed Python environment could not be started. Keep the launcher in the project folder.")
        }
    }

    func failed(_ message: String) {
        progress.stopAnimation(nil)
        progress.isHidden = true
        heading.stringValue = "PharmaGraph could not start"
        detail.stringValue = message
    }

    @objc func openBrowser() {
        if let url = address { NSWorkspace.shared.open(url) }
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        window.makeKeyAndOrderFront(nil)
        openBrowser()
        return true
    }

    func applicationWillTerminate(_ notification: Notification) {
        // Also handles quitting during startup: the helper lock serializes stop
        // after any in-progress start, preventing an orphaned background server.
        _ = runHelper(["--stop"])
    }
}

let app = NSApplication.shared
let delegate = PharmaGraphLauncher()
app.setActivationPolicy(.regular)
app.delegate = delegate
app.run()
