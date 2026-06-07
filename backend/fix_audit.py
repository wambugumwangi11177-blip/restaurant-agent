import re

with open('security_audit.py', 'r') as f:
    lines = f.readlines()

new_lines = []
for line in lines:
    if 'details=details or {}' in line:
        new_lines.append(line.replace('details=details or {}', 'details=json.dumps(details or {})'))
    else:
        new_lines.append(line)

with open('security_audit.py', 'w') as f:
    f.writelines(new_lines)
