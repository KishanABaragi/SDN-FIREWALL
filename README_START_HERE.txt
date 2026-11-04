Dynamic Firewall with Security Event Logger
====================================

1. Extract the complete project folder.
2. Open a terminal in the extracted SDN_FIREWALL_ONE_COMMAND folder.
3. Run: ./RUN_APP.sh
4. Keep the terminal open while using the dashboard.
5. Open http://127.0.0.1:8000/ if the browser does not open automatically.
6. Press Ctrl+C in the same terminal to stop the project.

The launcher performs the Mininet cleanup before Ryu starts. Do not run
'mn -c' manually while the application is running; it can kill Ryu.

Dashboard pages: Overview, Network map, Firewall controls, Test centre,
Event timeline, Performance and Quick guide.

Read README.md for the full architecture, test descriptions and dependencies.
Read TROUBLESHOOTING.md if startup or a test fails.
