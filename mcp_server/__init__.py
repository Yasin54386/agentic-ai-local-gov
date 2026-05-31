"""A real Model Context Protocol (MCP) server exposing the Darwin data + live
tools. Dependency-free: implements JSON-RPC 2.0 over stdio per the MCP spec, so
any MCP client (Claude Desktop, IDEs, the refresh scheduler) can connect.
"""
