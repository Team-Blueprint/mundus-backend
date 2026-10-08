import os

for root, _, files in os.walk("tests"):
    for file in files:
        if file.endswith(".py"):
            path = os.path.join(root, file)
            with open(path, "r") as f:
                content = f.read()
            
            # replacements
            content = content.replace('"supervisor"', '"contractor"')
            content = content.replace("supervisor@", "supervisor@") # keep email
            content = content.replace("supervisor_name", "name")
            content = content.replace("supervisor_email", "email")
            content = content.replace("supervisor_user_id", "user_id")
            content = content.replace("assigned_supervisor_id", "assigned_contractor_id")
            content = content.replace("supervisor_id", "user_id")
            
            # Specific fixes
            content = content.replace('"contractor_id": 1', '"contractor_id": "CTR-AK-003"')
            
            with open(path, "w") as f:
                f.write(content)
