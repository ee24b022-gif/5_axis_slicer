with open('backend/geometry_service.py', 'r') as f:
    lines = f.readlines()

new_lines = []
in_body = False
for i, line in enumerate(lines):
    if line.strip() == "emit(JobStage.MESH_VALIDATION, 0.0)":
        new_lines.append("        try:\n")
        new_lines.append("    " + line)
        in_body = True
    elif in_body:
        if line.strip() == "except JobCancelledError:":
            # Dedent the except JobCancelledError to match the new try
            new_lines.append("        except JobCancelledError:\n")
            in_body = False
        else:
            new_lines.append("    " + line if line != "\n" else line)
    else:
        new_lines.append(line)

with open('backend/geometry_service.py', 'w') as f:
    f.writelines(new_lines)
