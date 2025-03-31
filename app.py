from flask import session, redirect, url_for, request
from flask import Flask, render_template, request, jsonify
from pyVim.connect import SmartConnect, Disconnect
from pyVmomi import vim, vmodl
import json
import os
import subprocess
import pyotp
import time
import ssl

app = Flask(__name__)

# Initialize a list to store multiple configurations
vm_configs = []

# File paths
SECRET_FILE = "totp_secret.txt"
app.secret_key = "sZDSePDDHj"
USERS_FILE = "users.json"
AUTO_SIGNOUT_TIMEOUT = 300

def connect_vsphere(credentials_file):
    """
    Connect to vSphere using credentials from a JSON file.
    """
    try:
        # Load credentials
        with open(credentials_file, 'r') as f:
            creds = json.load(f)

        host = creds['host']
        user = creds['username']
        password = creds['password']

        # Disable SSL warnings for self-signed certificates
        context = ssl._create_unverified_context()

        # Connect to vSphere
        si = SmartConnect(host=host, user=user, pwd=password, sslContext=context)
        print(f"Connected to vSphere at {host}")
        return si
    except Exception as e:
        print(f"Failed to connect to vSphere: {e}")
        return None

def fetch_host_resources(service_instance):
    """
    Fetch resource details (CPU, RAM, Disk) for all hosts in clusters.
    """
    content = service_instance.RetrieveContent()
    host_data = []

    for datacenter in content.rootFolder.childEntity:
        if hasattr(datacenter, 'hostFolder'):
            clusters = datacenter.hostFolder.childEntity
            for cluster in clusters:
                if isinstance(cluster, vim.ClusterComputeResource):
                    for host in cluster.host:
                        summary = host.summary
                        hardware = summary.hardware
                        quick_stats = summary.quickStats

                        # Total and used resources
                        total_cpu_ghz = hardware.cpuMhz * hardware.numCpuCores / 1000
                        used_cpu_ghz = quick_stats.overallCpuUsage / 1000 if quick_stats.overallCpuUsage else 0
                        total_ram_gb = hardware.memorySize / (1024 ** 3)
                        used_ram_gb = quick_stats.overallMemoryUsage / 1024 if quick_stats.overallMemoryUsage else 0
                        total_disk_gb = sum(ds.summary.capacity for ds in host.datastore) / (1024 ** 3)
                        free_disk_gb = sum(ds.summary.freeSpace for ds in host.datastore) / (1024 ** 3)

                        # Append host details
                        host_info = {
                            "Host": summary.config.name,
                            "Cluster": cluster.name,
                            "Available CPU (GHz)": round(total_cpu_ghz - used_cpu_ghz, 1),
                            "Available RAM (GB)": round(total_ram_gb - used_ram_gb, 1),
                            "Available Disk (GB)": round(free_disk_gb, 1)
                        }
                        host_data.append(host_info)
    return host_data

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        # Get the form data
        username = request.form.get('username')
        password = request.form.get('password')

        # Load users from users.json
        with open(USERS_FILE, "r") as f:
            users = json.load(f)

        # Authenticate user
        if username in users and users[username] == password:
            session['user'] = username
            session['last_activity'] = time.time()  # Record the login time
            return redirect(url_for('index'))
        else:
            return render_template('login.html', error="Invalid credentials. Please try again.")

    # Render the login page
    return render_template('login.html')


# Logout Route
@app.route('/logout')
def logout():
    session.clear()  # Clear all session data
    return redirect(url_for('login'))

@app.before_request
def require_login():
    # Allow login, logout, and static assets without authentication
    allowed_routes = ['login', 'logout', 'static']

    if request.endpoint not in allowed_routes:
        # Check if user is logged in
        if 'user' not in session:
            return redirect(url_for('login'))

        # Check for inactivity timeout
        last_activity = session.get('last_activity')
        if last_activity and time.time() - last_activity > AUTO_SIGNOUT_TIMEOUT:
            session.clear()  # Clear all session data
            return redirect(url_for('login'))

        # Update the last activity timestamp
        session['last_activity'] = time.time()

@app.route('/')
def index():
    return render_template('index.html', username=session.get('user'))

@app.route('/get_host_resources', methods=['GET'])
def get_host_resources():
    """
    API endpoint to fetch available resources on hosts.
    """
    si = connect_vsphere("vsphere_credentials.json")
    if si:
        try:
            hosts = fetch_host_resources(si)  # Ensure fetch_host_resources is implemented correctly
            Disconnect(si)
            return jsonify(hosts)
        except Exception as e:
            return jsonify({"error": f"An error occurred: {str(e)}"}), 500
    else:
        return jsonify({"error": "Failed to connect to vSphere"}), 500


def generate_vm_spec(config_file, output_file):
    # Read the VM configuration from the config file
    with open(config_file, "r") as f:
        vm_configs = json.load(f)

    # Prepare the new format for the VM specs
    new_vm_specs = []
    for vm_config in vm_configs:
        base_name = vm_config["NameVM"]
        ip_list = vm_config["IPList"]
        count = vm_config["Count"]

        # Check if only one VM is being created
        if count == 1:
            # If Count is 1, don't append an index
            new_vm = {
                "NameVM": base_name,
                "CPU": vm_config["CPU"],
                "RAM": vm_config["RAM"],
                "Disk": vm_config["Disk"],
                "SourceVM": vm_config["SourceVM"],
                "Datastore": vm_config["Datastore"],
                "Network": vm_config["Network"],
                "IP": ip_list[0] if ip_list else "",  # Use first IP from IPList
                "SubnetMask": vm_config["SubnetMask"],
                "Gateway": vm_config["Gateway"],
                "DNS": vm_config["DNS"],
            }
            new_vm_specs.append(new_vm)
        else:
            # Generate VM specs with index if Count > 1
            for i in range(count):
                new_vm = {
                    "NameVM": f"{base_name}-{i+1}",
                    "CPU": vm_config["CPU"],
                    "RAM": vm_config["RAM"],
                    "Disk": vm_config["Disk"],
                    "SourceVM": vm_config["SourceVM"],
                    "Datastore": vm_config["Datastore"],
                    "Network": vm_config["Network"],
                    "IP": ip_list[i] if i < len(ip_list) else "",  # Ensure there's an IP address for each VM
                    "SubnetMask": vm_config["SubnetMask"],
                    "Gateway": vm_config["Gateway"],
                    "DNS": vm_config["DNS"],
                }
                new_vm_specs.append(new_vm)

    # Write the generated VM specs to the output file
    with open(output_file, "w") as outfile:
        json.dump(new_vm_specs, outfile, indent=4)

    print(f"VM specification generated and saved to {output_file}")

@app.route('/get_configured_vms', methods=['GET'])
def get_configured_vms():
    try:
        # Load data from vm_config.json for Configured VMs
        if os.path.exists('vm_config.json'):
            with open('vm_config.json', 'r') as f:
                configured_vms = json.load(f)
        else:
            configured_vms = []
        return jsonify(configured_vms)
    except FileNotFoundError:
        return jsonify([])

@app.route('/get_finalized_vms', methods=['GET'])
def get_finalized_vms():
    try:
        # Load data from vm_spec.json for Finalized VM Specifications
        if os.path.exists('vm_spec.json'):
            with open('vm_spec.json', 'r') as f:
                finalized_vms = json.load(f)
        else:
            finalized_vms = []
        return jsonify(finalized_vms)
    except FileNotFoundError:
        return jsonify([])

@app.route('/submit', methods=['POST'])
def submit():
    # Retrieve form data
    data = {
        "NameVM": request.form['NameVM'],
        "SourceVM": request.form['SourceVM'],
        "Count": int(request.form['Count']),
        "CPU": int(request.form['CPU']),
        "RAM": int(request.form['RAM']),
        "Disk": int(request.form['Disk']),
        "Datastore": request.form['Datastore'],
        "Network": request.form['Network'],
        "IPList": request.form['IPList'].split(','),
        "DNS": request.form['DNS'].split(','),
        "SubnetMask": request.form['SubnetMask'],
        "Gateway": request.form['Gateway']
    }

    # Append the new configuration to the list
    if os.path.exists('vm_config.json'):
        with open('vm_config.json', 'r') as f:
            existing_configs = json.load(f)
    else:
        existing_configs = []

    existing_configs.append(data)

    # Save the updated configurations to a JSON file
    with open('vm_config.json', 'w') as f:
        json.dump(existing_configs, f, indent=4)

    return jsonify({"message": "VM configuration added successfully"})

@app.route('/remove_vm/<int:index>', methods=['POST'])
def remove_vm(index):
    try:
        # Load existing configurations
        if os.path.exists('vm_config.json'):
            with open('vm_config.json', 'r') as f:
                vm_configs = json.load(f)
        else:
            return jsonify({"message": "No VMs to remove"}), 404

        # Remove the VM by index
        if 0 <= index < len(vm_configs):
            vm_configs.pop(index)
            with open('vm_config.json', 'w') as f:
                json.dump(vm_configs, f, indent=4)
            return jsonify({"message": "VM removed successfully"})
        else:
            return jsonify({"message": "Invalid index"}), 400
    except Exception as e:
        return jsonify({"message": "An error occurred while removing the VM", "error": str(e)}), 500

@app.route('/clear_all', methods=['POST'])
def clear_all():
    try:
        # Clear vm_config.json
        with open('vm_config.json', 'w') as f:
            json.dump([], f, indent=4)
        return jsonify({"message": "All VM configurations cleared successfully"})
    except Exception as e:
        return jsonify({"message": "An error occurred while clearing configurations", "error": str(e)}), 500

@app.route('/get_vsphere_host', methods=['GET'])
def get_vsphere_host():
    try:
        # Load the vSphere credentials
        with open('vsphere_credentials.json', 'r') as f:
            creds = json.load(f)
        return jsonify({"host": creds.get("host", "Unknown Host")})
    except FileNotFoundError:
        return jsonify({"error": "vsphere_credentials.json not found"}), 404
    except json.JSONDecodeError:
        return jsonify({"error": "Error reading vsphere_credentials.json"}), 500


@app.route('/create', methods=['POST'])
def create():
    try:
        # Use sys.executable to ensure the correct Python interpreter is used
        import sys
        result = subprocess.run([sys.executable, 'main.py'], capture_output=True, text=True)
        # Check if the process exited with an error
        if result.returncode != 0:
            return jsonify({
                "message": "An error occurred while running the process.",
                "error": result.stderr.strip()
            }), 500
        return jsonify({"message": "Creation process started", "output": result.stdout.strip()})
    except Exception as e:
        return jsonify({
            "message": "An unexpected error occurred.",
            "error": str(e)
        }), 500

@app.route('/finalize', methods=['POST'])
def finalize():
    try:
        # Call the generate_vm_spec function
        generate_vm_spec('vm_config.json', 'vm_spec.json')
        return jsonify({"message": "VM specifications finalized and saved."})
    except Exception as e:
        return jsonify({"message": "An error occurred during finalization", "error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
