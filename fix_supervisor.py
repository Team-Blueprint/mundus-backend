import os

def replace_in_file(filepath):
    with open(filepath, 'r') as f:
        content = f.read()

    # Case sensitive replacements
    content = content.replace("supervisor_user", "contractor_user")
    content = content.replace("supervisor", "contractor")
    content = content.replace("Supervisor", "Contractor")
    content = content.replace("SUPERVISOR", "CONTRACTOR")

    with open(filepath, 'w') as f:
        f.write(content)

for root, _, files in os.walk("app"):
    for file in files:
        if file.endswith(".py"):
            replace_in_file(os.path.join(root, file))

print("Replacements complete in app/")
