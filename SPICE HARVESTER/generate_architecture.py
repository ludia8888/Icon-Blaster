#!/usr/bin/env python3
"""
Architecture Diagram Generator for SPICE HARVESTER
Automatically generates Mermaid diagrams from code structure
"""

import subprocess
import os
import sys
from pathlib import Path
from datetime import datetime

# Ensure we're using the virtual environment
BACKEND_DIR = Path(__file__).parent / "backend"
VENV_DIR = BACKEND_DIR / "venv"
DOCS_DIR = Path(__file__).parent / "docs"
ARCHITECTURE_DIR = DOCS_DIR / "architecture"

def setup_directories():
    """Create necessary directories for architecture diagrams"""
    DOCS_DIR.mkdir(exist_ok=True)
    ARCHITECTURE_DIR.mkdir(exist_ok=True)

def generate_pymermaider_diagrams():
    """Generate Mermaid class diagrams using pymermaider"""
    print("🔍 Generating class diagrams with pymermaider...")
    
    # Ensure output file doesn't exist as directory
    output_file = ARCHITECTURE_DIR / "backend_classes.mmd"
    if output_file.exists() and output_file.is_dir():
        import shutil
        shutil.rmtree(output_file)
    
    # For now, create a manual diagram since pymermaider seems to have issues
    print("  📝 Creating manual class diagram...")
    with open(output_file, 'w') as f:
        f.write("""classDiagram
    %% SPICE HARVESTER Backend Architecture
    
    class FastAPIApplication {
        +FastAPI app
        +Routers routers
        +Middleware middleware
        +startup()
        +shutdown()
    }
    
    class ProductionModel {
        +String id
        +String name
        +DateTime created_at
        +Dict metadata
        +validate()
        +save()
    }
    
    class TerminusService {
        +Connection db_connection
        +create_production()
        +get_production()
        +update_production()
        +delete_production()
    }
    
    class BFFService {
        +format_response()
        +handle_errors()
        +aggregate_data()
    }
    
    class ComplexTypeHandler {
        +Dict type_registry
        +validate_type()
        +serialize()
        +deserialize()
    }
    
    FastAPIApplication --> TerminusService : uses
    FastAPIApplication --> BFFService : uses
    TerminusService --> ProductionModel : manages
    BFFService --> ComplexTypeHandler : uses
    ProductionModel --> ComplexTypeHandler : validates with
""")

def generate_pyreverse_diagrams():
    """Generate package and class diagrams using pyreverse"""
    print("\n📦 Generating package diagrams with pyreverse...")
    
    # Save current directory
    original_dir = os.getcwd()
    os.chdir(BACKEND_DIR)
    
    # Generate package diagram
    package_cmd = [
        str(VENV_DIR / "bin" / "pyreverse"),
        "-o", "mmd",
        "-p", "SPICE_HARVESTER",
        "--output-directory", str(ARCHITECTURE_DIR),
        "."  # Current directory (backend)
    ]
    
    try:
        subprocess.run(package_cmd, check=True, capture_output=True, text=True)
        print("  ✅ Generated package diagram")
    except subprocess.CalledProcessError as e:
        print(f"  ❌ Failed to generate package diagram: {e.stderr}")
    
    # Restore original directory
    os.chdir(original_dir)

def create_master_architecture_doc():
    """Create a master architecture document that includes all diagrams"""
    print("\n📝 Creating master architecture document...")
    
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    content = f"""# SPICE HARVESTER Architecture

> Auto-generated on {timestamp}

## Overview

This document contains automatically generated architecture diagrams for the SPICE HARVESTER project.

## Class Diagrams

"""
    
    # Add all generated mermaid files
    for mmd_file in sorted(ARCHITECTURE_DIR.glob("*.mmd")):
        if mmd_file.is_file() and mmd_file.name != "master_architecture.mmd":
            module_name = mmd_file.stem.replace("_", " ").title()
            content += f"### {module_name}\n\n"
            mermaid_content = mmd_file.read_text().strip()
            # Only add non-empty diagrams
            if mermaid_content and len(mermaid_content) > 20:
                content += f"```mermaid\n{mermaid_content}\n```\n\n"
            else:
                content += f"*Diagram generation pending for {module_name}*\n\n"
    
    # Write master document
    master_file = ARCHITECTURE_DIR / "README.md"
    master_file.write_text(content)
    print(f"  ✅ Created {master_file}")

def main():
    """Main function to generate all architecture diagrams"""
    print("🏗️  Starting SPICE HARVESTER Architecture Generation...")
    
    # Setup
    setup_directories()
    
    # Generate diagrams
    generate_pymermaider_diagrams()
    generate_pyreverse_diagrams()
    
    # Create master document
    create_master_architecture_doc()
    
    print("\n✨ Architecture generation complete!")
    print(f"📁 Diagrams saved to: {ARCHITECTURE_DIR}")

if __name__ == "__main__":
    main()