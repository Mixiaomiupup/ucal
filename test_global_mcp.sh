#!/bin/bash
# Test UCAL Global MCP Registration

echo "=== Testing UCAL Global MCP ==="
echo ""

echo "1. Checking MCP server status..."
claude mcp list | grep ucal
echo ""

echo "2. Testing UCAL in a new session..."
echo "   Starting fresh Claude Code session to verify tools..."
echo ""
echo "   Run this in a NEW terminal:"
echo "   cd /Users/mixiaomiupup && claude"
echo ""
echo "   Then ask Claude: 'Show me all available ucal tools'"
echo ""

echo "3. Expected tools after restart:"
echo "   - ucal_platform_login"
echo "   - ucal_platform_search"
echo "   - ucal_platform_read"
echo "   - ucal_platform_extract"
echo "   - ucal_browser_action"
echo ""

echo "=== Configuration Summary ==="
echo "Global MCP: ~/.claude.json (✓ updated)"
echo "Project MCP: /Users/mixiaomiupup/projects/ucal/.claude.json (✓ removed)"
echo ""
echo "To use UCAL globally, restart Claude Code!"
