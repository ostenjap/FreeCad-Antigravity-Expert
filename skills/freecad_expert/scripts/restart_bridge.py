import FreeCAD as App
import FreeCADGui
import sys
import os

# Robust MCP Bridge Restart Script
# Use this to revive the bridge if it crashes during complex modeling

def restart_bridge():
    try:
        # Try to stop existing bridge if it's hanging
        FreeCADGui.runCommand("Stop_MCP_Bridge")
        print("Stopping existing bridge...")
    except:
        pass

    try:
        # Re-initialize the plugin manually
        from freecad_mcp_bridge.server import FreecadMCPPlugin
        from freecad_mcp_bridge.bridge_utils import register_mcp_plugin
        
        # Default ports for the bridge
        xmlrpc_port = 9875
        socket_port = 9874
        
        print(f"Starting Robust MCP Bridge on port {xmlrpc_port}...")
        plugin = FreecadMCPPlugin(
            host="localhost",
            port=socket_port,
            xmlrpc_port=xmlrpc_port,
            enable_xmlrpc=True,
        )
        plugin.start()
        register_mcp_plugin(plugin, xmlrpc_port, socket_port)
        print("Bridge restarted successfully!")
    except Exception as e:
        print(f"Failed to restart bridge: {e}")

if __name__ == "__main__":
    restart_bridge()
