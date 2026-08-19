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

    # Create and show main window
    cwd = Path(os.getcwd())
    win = MainWindow(cwd)
    win.show()

    # Run application
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
