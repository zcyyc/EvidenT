# AIOps MCP Project
## Project Overview
This is an AI-based Operations (AIOps) project focused on automated software package repair and root cause analysis. The project leverages machine learning and natural language processing techniques to analyze build failures, retrieve historical cases, and provide automated repair solutions.

## Project Structure
```
aiops_pro/
├── client.py                # Client implementation for connecting to MCP server
├── server.py               # Server implementation providing various tools and APIs
├── config/                 # Configuration files directory
│   └── paths.yaml          # Path configurations
├── dataset/                # Dataset directory
│   └── obs_data/           # OBS data
│       └── risc_v/         # RISC-V architecture related data
│           └── failed_postquantumcryptoengine  # The build failed postquantumcryptoengine package
├── temp_workspace/         # Temporary workspace for repair
│   └── postquantumcryptoengine/  # Temporary workspace for postquantumcryptoengine package; now it is the succeed build repaired by MCPacher
└── mcp_server_tools/       # Server tools collection
    ├── auto_repair/        # Automated repair tools
    │   ├── check_build_res.py    # Check build results
    │   ├── get_repo_structure.py # Get repository structure
    │   └── upload_files.py       # File upload tools
    └── rca_tools/          # Root Cause Analysis tools
        ├── ad/             # Anomaly detection
        ├── anomaly_detection.py  # Anomaly detection implementation
        ├── arch_know_search.py   # Architecture knowledge search
        ├── spec_directive.py     # Specification directive
        └── historical_case.py    # Historical case retrieval
```

## Key Features
### 1. Automated Repair
- Repository Structure Analysis : Analyze project structure, identify key components and dependencies
- Build Result Verification : Automatically check OBS build results and identify failure reasons
- File Upload : Support for uploading repaired files to target locations
### 2. Root Cause Analysis
- Anomaly Detection : Identify anomalous patterns in logs and build processes
- Architecture Knowledge Search : Search relevant architectural knowledge based on TF-IDF vectorization
- Historical Case Retrieval : Retrieve similar historical failure cases to provide reference solutions
### 3. Client-Server Architecture
- Lightweight Client : Connects to the MCP server, processes packages sequentially for repair
- Feature-rich Server : Provides tool APIs, supports history caching and deduplication

## Usage
### Activate the virtual environment
```
uv init
source .venv/bin/activate
uv pip install -r requirements.txt
```

### Run the client and rebuild packages
```
python client.py
```


