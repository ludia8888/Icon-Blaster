#!/usr/bin/env python3
"""
Clean up TODO/FIXME/HACK/XXX comments by creating GitHub issues
and updating the code with issue references
"""
import os
import re
from pathlib import Path
from typing import List, Tuple, Dict
from datetime import datetime
import json


class TodoComment:
    def __init__(self, file_path: str, line_num: int, comment_type: str, content: str, context: str = ""):
        self.file_path = file_path
        self.line_num = line_num
        self.comment_type = comment_type  # TODO, FIXME, HACK, XXX
        self.content = content
        self.context = context
        self.priority = self._determine_priority()
    
    def _determine_priority(self) -> str:
        """Determine priority based on comment type and content"""
        if self.comment_type in ["FIXME", "XXX"]:
            return "high"
        elif self.comment_type == "HACK":
            return "medium"
        elif "security" in self.content.lower() or "vulnerability" in self.content.lower():
            return "high"
        elif "performance" in self.content.lower() or "optimize" in self.content.lower():
            return "medium"
        else:
            return "low"
    
    def to_dict(self) -> Dict:
        return {
            "file": self.file_path,
            "line": self.line_num,
            "type": self.comment_type,
            "content": self.content,
            "priority": self.priority,
            "context": self.context
        }


def find_todo_comments(directory: str = ".") -> List[TodoComment]:
    """Find all TODO/FIXME/HACK/XXX comments in Python files"""
    comments = []
    pattern = re.compile(r'#\s*(TODO|FIXME|HACK|XXX)\s*:?\s*(.+)$', re.IGNORECASE)
    
    for root, dirs, filenames in os.walk(directory):
        # Skip directories
        dirs[:] = [d for d in dirs if d not in ['venv', '.venv', '__pycache__', '.git', 'archive_*']]
        
        for filename in filenames:
            if filename.endswith('.py'):
                filepath = Path(root) / filename
                relative_path = filepath.relative_to(directory)
                
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        lines = f.readlines()
                        
                    for i, line in enumerate(lines, 1):
                        match = pattern.search(line)
                        if match:
                            comment_type = match.group(1).upper()
                            content = match.group(2).strip()
                            
                            # Get context (previous and next line)
                            context_lines = []
                            if i > 1:
                                context_lines.append(f"L{i-1}: {lines[i-2].strip()}")
                            context_lines.append(f"L{i}: {lines[i-1].strip()}")
                            if i < len(lines):
                                context_lines.append(f"L{i+1}: {lines[i].strip()}")
                            
                            context = "\n".join(context_lines)
                            
                            comment = TodoComment(
                                str(relative_path),
                                i,
                                comment_type,
                                content,
                                context
                            )
                            comments.append(comment)
                
                except Exception as e:
                    print(f"Error reading {filepath}: {e}")
    
    return comments


def create_issue_template(comment: TodoComment) -> str:
    """Create GitHub issue template for a TODO comment"""
    template = f"""## {comment.comment_type}: {comment.content}

**File**: `{comment.file_path}`
**Line**: {comment.line_num}
**Priority**: {comment.priority}

### Context
```python
{comment.context}
```

### Description
{comment.content}

### Tasks
- [ ] Analyze the requirement
- [ ] Implement the solution
- [ ] Add tests if applicable
- [ ] Update documentation if needed

### Additional Notes
This issue was automatically created from a {comment.comment_type} comment in the code.
"""
    return template


def generate_report(comments: List[TodoComment]) -> str:
    """Generate a summary report of all TODO comments"""
    report = f"""# TODO Comments Report
Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Total comments found: {len(comments)}

## Summary by Type
"""
    
    # Count by type
    by_type = {}
    for comment in comments:
        by_type[comment.comment_type] = by_type.get(comment.comment_type, 0) + 1
    
    for comment_type, count in sorted(by_type.items()):
        report += f"- {comment_type}: {count}\n"
    
    report += "\n## Summary by Priority\n"
    
    # Count by priority
    by_priority = {"high": 0, "medium": 0, "low": 0}
    for comment in comments:
        by_priority[comment.priority] += 1
    
    for priority, count in by_priority.items():
        report += f"- {priority.capitalize()}: {count}\n"
    
    report += "\n## Comments by File\n"
    
    # Group by file
    by_file = {}
    for comment in comments:
        if comment.file_path not in by_file:
            by_file[comment.file_path] = []
        by_file[comment.file_path].append(comment)
    
    for file_path, file_comments in sorted(by_file.items()):
        report += f"\n### {file_path}\n"
        for comment in sorted(file_comments, key=lambda x: x.line_num):
            report += f"- Line {comment.line_num}: **{comment.comment_type}** - {comment.content}\n"
    
    return report


def export_to_json(comments: List[TodoComment], output_file: str = "todo_comments.json"):
    """Export comments to JSON for further processing"""
    data = {
        "generated_at": datetime.now().isoformat(),
        "total_comments": len(comments),
        "comments": [comment.to_dict() for comment in comments]
    }
    
    with open(output_file, 'w') as f:
        json.dump(data, f, indent=2)
    
    print(f"Exported {len(comments)} comments to {output_file}")


def main():
    """Main function"""
    print("Scanning for TODO/FIXME/HACK/XXX comments...")
    
    # Find all comments
    comments = find_todo_comments('.')
    
    if not comments:
        print("No TODO comments found!")
        return
    
    print(f"Found {len(comments)} TODO comments")
    
    # Generate report
    report = generate_report(comments)
    with open('TODO_REPORT.md', 'w') as f:
        f.write(report)
    print("Generated TODO_REPORT.md")
    
    # Export to JSON
    export_to_json(comments)
    
    # Create issue templates for high priority items
    high_priority = [c for c in comments if c.priority == "high"]
    if high_priority:
        issues_dir = Path("github_issues")
        issues_dir.mkdir(exist_ok=True)
        
        for i, comment in enumerate(high_priority[:10]):  # Limit to 10 issues
            issue_content = create_issue_template(comment)
            issue_file = issues_dir / f"issue_{i+1}_{comment.comment_type.lower()}.md"
            with open(issue_file, 'w') as f:
                f.write(issue_content)
        
        print(f"Created {min(len(high_priority), 10)} GitHub issue templates in github_issues/")
    
    # Summary
    print("\nSummary:")
    print(f"- Total comments: {len(comments)}")
    print(f"- High priority: {len([c for c in comments if c.priority == 'high'])}")
    print(f"- Medium priority: {len([c for c in comments if c.priority == 'medium'])}")
    print(f"- Low priority: {len([c for c in comments if c.priority == 'low'])}")


if __name__ == "__main__":
    main()