#!/usr/bin/env python3
"""
Migration script to update codebase to use secure database clients
This script helps replace vulnerable database client usage with secure versions
"""
import os
import re
import argparse
from pathlib import Path
from typing import List, Tuple, Dict, Any
from datetime import datetime


class DatabaseClientMigrator:
    """Migrates database client usage to secure versions"""
    
    def __init__(self, project_root: str, dry_run: bool = True):
        self.project_root = Path(project_root)
        self.dry_run = dry_run
        self.changes_made = []
        
        # Patterns to identify database client imports and usage
        self.import_patterns = {
            'sqlite': [
                (r'from database\.clients\.sqlite_client import SQLiteClient',
                 'from database.clients.sqlite_client_secure import SQLiteClientSecure'),
                (r'from \.sqlite_client import SQLiteClient',
                 'from .sqlite_client_secure import SQLiteClientSecure'),
                (r'import database\.clients\.sqlite_client',
                 'import database.clients.sqlite_client_secure_secure'),
            ],
            'postgres': [
                (r'from database\.clients\.postgres_client import PostgresClient',
                 'from database.clients.postgres_client_secure import PostgresClientSecure'),
                (r'from \.postgres_client import PostgresClient',
                 'from .postgres_client_secure import PostgresClientSecure'),
                (r'import database\.clients\.postgres_client',
                 'import database.clients.postgres_client_secure_secure'),
            ]
        }
        
        # Class instantiation patterns
        self.class_patterns = {
            'sqlite': [
                (r'SQLiteClient\s*\(', 'SQLiteClientSecure('),
            ],
            'postgres': [
                (r'PostgresClient\s*\(', 'PostgresClientSecure('),
            ]
        }
        
        # Files to exclude from migration
        self.exclude_patterns = [
            '**/tests/**',
            '**/test_*.py',
            '**/*_test.py',
            '**/archive_*/**',
            '**/scripts/migrate_to_secure_db_clients.py',
            '**/database/clients/sqlite_client.py',
            '**/database/clients/postgres_client.py',
            '**/database/clients/sqlite_client_secure.py',
            '**/database/clients/postgres_client_secure.py',
        ]
    
    def should_process_file(self, file_path: Path) -> bool:
        """Check if file should be processed"""
        # Only process Python files
        if not file_path.suffix == '.py':
            return False
        
        # Check exclusions
        for pattern in self.exclude_patterns:
            if file_path.match(pattern):
                return False
        
        return True
    
    def find_files_to_migrate(self) -> List[Path]:
        """Find all Python files that might need migration"""
        files_to_check = []
        
        for py_file in self.project_root.rglob("*.py"):
            if self.should_process_file(py_file):
                # Quick check if file contains database client references
                try:
                    content = py_file.read_text(encoding='utf-8')
                    if ('SQLiteClient' in content or 'PostgresClient' in content or
                        'sqlite_client' in content or 'postgres_client' in content):
                        files_to_check.append(py_file)
                except Exception as e:
                    print(f"Error reading {py_file}: {e}")
        
        return files_to_check
    
    def migrate_file(self, file_path: Path) -> bool:
        """Migrate a single file to use secure clients"""
        try:
            original_content = file_path.read_text(encoding='utf-8')
            content = original_content
            changes = []
            
            # Apply import replacements
            for db_type, patterns in self.import_patterns.items():
                for old_pattern, new_pattern in patterns:
                    if re.search(old_pattern, content):
                        content = re.sub(old_pattern, new_pattern, content)
                        changes.append(f"Updated {db_type} import")
            
            # Apply class instantiation replacements
            for db_type, patterns in self.class_patterns.items():
                for old_pattern, new_pattern in patterns:
                    if re.search(old_pattern, content):
                        content = re.sub(old_pattern, new_pattern, content)
                        changes.append(f"Updated {db_type} class instantiation")
            
            # Check if any changes were made
            if content != original_content:
                if not self.dry_run:
                    # Create backup
                    backup_path = file_path.with_suffix('.py.bak')
                    file_path.rename(backup_path)
                    
                    # Write updated content
                    file_path.write_text(content, encoding='utf-8')
                    
                    self.changes_made.append({
                        'file': str(file_path.relative_to(self.project_root)),
                        'changes': changes,
                        'backup': str(backup_path)
                    })
                else:
                    self.changes_made.append({
                        'file': str(file_path.relative_to(self.project_root)),
                        'changes': changes,
                        'backup': None
                    })
                
                return True
            
        except Exception as e:
            print(f"Error migrating {file_path}: {e}")
        
        return False
    
    def generate_report(self) -> str:
        """Generate migration report"""
        report = []
        report.append("# Database Client Migration Report")
        report.append(f"Generated at: {datetime.now().isoformat()}")
        report.append(f"Mode: {'DRY RUN' if self.dry_run else 'ACTUAL MIGRATION'}")
        report.append("")
        
        if self.changes_made:
            report.append(f"## Files Modified: {len(self.changes_made)}")
            report.append("")
            
            for change in self.changes_made:
                report.append(f"### {change['file']}")
                report.append("Changes:")
                for c in change['changes']:
                    report.append(f"  - {c}")
                if change['backup']:
                    report.append(f"Backup: {change['backup']}")
                report.append("")
        else:
            report.append("No files needed migration.")
        
        return "\n".join(report)
    
    def run(self) -> Dict[str, Any]:
        """Run the migration process"""
        print(f"Starting database client migration {'(DRY RUN)' if self.dry_run else ''}...")
        print(f"Project root: {self.project_root}")
        
        # Find files to migrate
        files_to_check = self.find_files_to_migrate()
        print(f"Found {len(files_to_check)} files to check")
        
        # Migrate each file
        migrated_count = 0
        for file_path in files_to_check:
            if self.migrate_file(file_path):
                migrated_count += 1
                print(f"{'Would migrate' if self.dry_run else 'Migrated'}: {file_path.relative_to(self.project_root)}")
        
        # Generate report
        report = self.generate_report()
        
        # Save report
        report_path = self.project_root / f"MIGRATION_REPORT_{'DRY_RUN' if self.dry_run else 'ACTUAL'}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        report_path.write_text(report, encoding='utf-8')
        print(f"\nMigration report saved to: {report_path}")
        
        return {
            'files_checked': len(files_to_check),
            'files_migrated': migrated_count,
            'report_path': str(report_path),
            'changes': self.changes_made
        }


def main():
    parser = argparse.ArgumentParser(description='Migrate database clients to secure versions')
    parser.add_argument(
        '--project-root',
        type=str,
        default='.',
        help='Project root directory (default: current directory)'
    )
    parser.add_argument(
        '--execute',
        action='store_true',
        help='Actually perform the migration (default is dry run)'
    )
    parser.add_argument(
        '--restore',
        action='store_true',
        help='Restore from backup files (*.py.bak)'
    )
    
    args = parser.parse_args()
    
    if args.restore:
        # Restore from backups
        project_root = Path(args.project_root)
        restored = 0
        
        for backup_file in project_root.rglob("*.py.bak"):
            original_file = backup_file.with_suffix('')
            try:
                # Remove current file if exists
                if original_file.exists():
                    original_file.unlink()
                
                # Rename backup to original
                backup_file.rename(original_file)
                restored += 1
                print(f"Restored: {original_file.relative_to(project_root)}")
            except Exception as e:
                print(f"Error restoring {backup_file}: {e}")
        
        print(f"\nRestored {restored} files from backups")
    else:
        # Run migration
        migrator = DatabaseClientMigrator(
            project_root=args.project_root,
            dry_run=not args.execute
        )
        
        results = migrator.run()
        
        print("\n" + "="*50)
        print("Migration Summary:")
        print(f"  Files checked: {results['files_checked']}")
        print(f"  Files {'would be' if not args.execute else ''} migrated: {results['files_migrated']}")
        print(f"  Report: {results['report_path']}")
        
        if not args.execute:
            print("\nThis was a DRY RUN. To actually perform the migration, run with --execute")


if __name__ == "__main__":
    main()