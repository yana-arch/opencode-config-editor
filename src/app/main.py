# Overridden by build.py when generating a per-adapter single-file artifact
# (e.g. openclaude-config-editor.py sets this to "openclaude").
_BUILD_DEFAULT_ADAPTER = None


def main():
    """Main application entry point"""
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)

    # Set application style
    app.setStyle("Fusion")

    # Set default font size
    settings = SettingsManager()
    font = QApplication.font()
    font.setPointSize(settings.get_font_size())
    QApplication.setFont(font)

    # Select the agent adapter: --adapter=<name> or CONFIG_EDITOR_ADAPTER env,
    # then the build-time default, else the first registered (opencode).
    adapter_name = None
    for arg in sys.argv[1:]:
        if arg.startswith("--adapter="):
            adapter_name = arg.split("=", 1)[1]
    adapter_name = adapter_name or os.environ.get("CONFIG_EDITOR_ADAPTER") or _BUILD_DEFAULT_ADAPTER
    adapter = get_adapter(adapter_name) if adapter_name else None

    # Create and show main window
    cwd = Path(os.getcwd())
    win = MainWindow(cwd, adapter=adapter)
    win.show()

    # Run application
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
