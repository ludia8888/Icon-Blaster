#!/usr/bin/env python3
"""
Archive unused files safely
"""
import json
import os
import shutil
from pathlib import Path
from datetime import datetime

# Load results
with open('unused_files_final.json', 'r') as f:
    results = json.load(f)

unused_files = results['all_unused']
archive_dir = Path('archive_legacy_' + datetime.now().strftime('%Y%m%d'))

print(f"📦 Archiving {len(unused_files)} unused files to {archive_dir}/")

# Create archive directory
archive_dir.mkdir(exist_ok=True)

# Create archive info
archive_info = {
    'archived_date': datetime.now().isoformat(),
    'reason': 'No references found in codebase',
    'total_files': len(unused_files),
    'files': unused_files,
    'analysis_method': 'grep-based reference check across all Python, YAML, JSON, and shell files'
}

with open(archive_dir / 'ARCHIVE_INFO.json', 'w') as f:
    json.dump(archive_info, f, indent=2)

# Archive files
archived = 0
errors = []

for file in unused_files:
    try:
        source = Path(file)
        if source.exists():
            # Create directory structure in archive
            dest_dir = archive_dir / source.parent
            dest_dir.mkdir(parents=True, exist_ok=True)
            
            # Move file
            dest = archive_dir / file
            shutil.move(str(source), str(dest))
            archived += 1
            
            # Remove empty parent directories
            parent = source.parent
            while parent != Path('.') and not any(parent.iterdir()):
                parent.rmdir()
                parent = parent.parent
                
    except Exception as e:
        errors.append({'file': file, 'error': str(e)})
        print(f"❌ Error archiving {file}: {e}")

# Create recovery script
recovery_script = f'''#!/bin/bash
# Recovery script for archived files
# Generated on {datetime.now().isoformat()}

echo "🔄 Recovering {len(unused_files)} files from archive..."

'''

for file in unused_files:
    recovery_script += f'mv "{archive_dir}/{file}" "{file}" 2>/dev/null\n'

recovery_script += '''
echo "✅ Recovery complete"
'''

with open(archive_dir / 'recover.sh', 'w') as f:
    f.write(recovery_script)

os.chmod(archive_dir / 'recover.sh', 0o755)

# Summary
print(f"\n📊 Archive Summary:")
print(f"✅ Successfully archived: {archived} files")
print(f"❌ Errors: {len(errors)} files")
print(f"📁 Archive location: {archive_dir}/")
print(f"🔄 Recovery script: {archive_dir}/recover.sh")

if errors:
    print(f"\n⚠️  Files with errors:")
    for err in errors[:5]:
        print(f"  - {err['file']}: {err['error']}")

# Create a summary file
summary = f"""Legacy Code Archive Summary
==========================
Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}
Total files archived: {archived}
Archive location: {archive_dir}/

To recover all files:
  ./{archive_dir}/recover.sh

Files archived by category:
"""

for category, files in results['unused_by_category'].items():
    if files:
        summary += f"\n{category.upper()} ({len(files)} files):\n"
        for file in files[:3]:
            summary += f"  - {file}\n"
        if len(files) > 3:
            summary += f"  ... and {len(files) - 3} more\n"

with open(archive_dir / 'README.md', 'w') as f:
    f.write(summary)

print(f"\n✅ Archive complete! See {archive_dir}/README.md for details")