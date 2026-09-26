# MCP Design

Status: **scheduled for M5**.

V1 includes one self-built Document MCP Server exposing:

```text
search_documents
get_document
get_document_page
find_clause
```

DocMind-Agent consumes the server through an MCP client adapter.

The V1 goal is not a general MCP platform. The goal is to demonstrate a real MCP Server/Client integration, tool discovery/registration, structured inputs/outputs, timeout handling and error propagation inside Agent execution.
