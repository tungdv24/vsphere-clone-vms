import json
from pyVim.connect import SmartConnect, Disconnect
from pyVmomi import vim, vmodl
import ssl

# Disable SSL warnings
ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

# Function to connect to vSphere
def connect_vsphere(host, user, pwd):
    try:
        print("Connecting to vSphere...")
        service_instance = SmartConnect(host=host, user=user, pwd=pwd, sslContext=ssl_context)
        print("Login successful!")
        return service_instance
    except Exception as e:
        print(f"Failed to connect to vSphere: {e}")
        exit(1)

# Function to find a VM by name
def get_vm_by_name(content, vm_name):
    obj_view = content.viewManager.CreateContainerView(content.rootFolder, [vim.VirtualMachine], True)
    try:
        for vm in obj_view.view:
            if vm.name == vm_name:
                print(f"Found VM: {vm_name}")
                return vm
        print(f"VM not found: {vm_name}")
        return None
    finally:
        obj_view.Destroy()

# Function to clone a VM
def clone_vm(content, source_vm_name, vm_config):
    try:
        source_vm = get_vm_by_name(content, source_vm_name)
        if not source_vm:
            print(f"Source VM '{source_vm_name}' not found! Skipping...")
            return {"NameVM": vm_config['NameVM'], "Status": "Failure"}

        dest_folder = source_vm.parent

        # Get resource pool if specified, else use the source VM's pool
        resource_pool = None
        if 'ResourcePool' in vm_config and vm_config['ResourcePool']:
            resource_pool = get_resource_pool(content, vm_config['ResourcePool'])
        else:
            resource_pool = source_vm.resourcePool

        relocate_spec = vim.vm.RelocateSpec()
        relocate_spec.datastore = get_datastore(content, vm_config['Datastore'])
        relocate_spec.pool = resource_pool

        config_spec = vim.vm.ConfigSpec()
        config_spec.numCPUs = vm_config['CPU']
        config_spec.memoryMB = vm_config['RAM'] * 1024
        config_spec.deviceChange = create_disk_and_network_changes(source_vm, content, vm_config)

        clone_spec = vim.vm.CloneSpec()
        clone_spec.location = relocate_spec
        clone_spec.powerOn = True
        clone_spec.config = config_spec
        clone_spec.customization = create_customization_spec(content, vm_config)

        task = source_vm.Clone(name=vm_config['NameVM'], folder=dest_folder, spec=clone_spec)
        wait_for_task(task)
        print(f"VM {vm_config['NameVM']} created successfully.")
        return {"NameVM": vm_config['NameVM'], "Status": "Success"}

    except Exception as e:
        print(f"Failed to create VM {vm_config['NameVM']}: {e}")
        return {"NameVM": vm_config['NameVM'], "Status": "Failure"}

# Function to get datastore
def get_datastore(content, datastore_name):
    obj_view = content.viewManager.CreateContainerView(content.rootFolder, [vim.Datastore], True)
    try:
        for datastore in obj_view.view:
            if datastore.name == datastore_name:
                print(f"Found datastore: {datastore_name}")
                return datastore
        raise ValueError(f"Datastore '{datastore_name}' not found!")
    finally:
        obj_view.Destroy()

# Function to create disk and network changes
def create_disk_and_network_changes(source_vm, content, vm_config):
    changes = []

    # Adjust disk size
    for device in source_vm.config.hardware.device:
        if isinstance(device, vim.vm.device.VirtualDisk):
            disk_spec = vim.vm.device.VirtualDeviceSpec()
            disk_spec.operation = vim.vm.device.VirtualDeviceSpec.Operation.edit
            disk_spec.device = device
            disk_spec.device.capacityInKB = vm_config['Disk'] * 1024 * 1024
            changes.append(disk_spec)

    # Adjust network
    network = get_network(content, vm_config['Network'])
    nics = [dev for dev in source_vm.config.hardware.device if isinstance(dev, vim.vm.device.VirtualEthernetCard)]
    if not nics:
        raise ValueError("No network interface card found on source VM.")
    nic_spec = vim.vm.device.VirtualDeviceSpec()
    nic_spec.operation = vim.vm.device.VirtualDeviceSpec.Operation.edit
    nic_spec.device = nics[0]
    nic_spec.device.backing = vim.vm.device.VirtualEthernetCard.NetworkBackingInfo(
        network=network, deviceName=vm_config['Network']
    )
    nic_spec.device.addressType = "generated"
    changes.append(nic_spec)

    return changes

# Function to get network
def get_network(content, network_name):
    obj_view = content.viewManager.CreateContainerView(content.rootFolder, [vim.Network], True)
    try:
        for network in obj_view.view:
            if network.name == network_name:
                print(f"Found network: {network_name}")
                return network
        raise ValueError(f"Network '{network_name}' not found!")
    finally:
        obj_view.Destroy()

# Function to create customization spec
def create_customization_spec(content, vm_config):
    global_ip = vim.vm.customization.GlobalIPSettings()
    global_ip.dnsServerList = vm_config['DNS']

    adapter_mapping = vim.vm.customization.AdapterMapping()
    adapter_mapping.adapter = vim.vm.customization.IPSettings(
        ip=vim.vm.customization.FixedIp(ipAddress=vm_config['IP']),
        subnetMask=vm_config['SubnetMask'],
        gateway=vm_config['Gateway']
    )

    ident = vim.vm.customization.LinuxPrep(
        hostName=vim.vm.customization.FixedName(name=vm_config['NameVM']),
        domain="local"
    )

    custom_spec = vim.vm.customization.Specification()
    custom_spec.nicSettingMap = [adapter_mapping]
    custom_spec.globalIPSettings = global_ip
    custom_spec.identity = ident

    return custom_spec

# Function to wait for task completion
def wait_for_task(task):
    import time
    while task.info.state == vim.TaskInfo.State.running:
        time.sleep(5)  # Avoid busy waiting
    if task.info.state == vim.TaskInfo.State.success:
        print("Task completed successfully.")
    else:
        print(f"Task failed: {task.info.error.localizedMessage if task.info.error else 'Unknown error'}")

# Main function
def main():
    credentials_file = "vsphere_credentials.json"
    output_file = "vm_spec.json"


    # Step 4: Load credentials and connect to vSphere
    try:
        with open(credentials_file, "r") as cred_file:
            creds = json.load(cred_file)
    except (json.JSONDecodeError, FileNotFoundError) as e:
        print(f"Error reading credentials file: {e}")
        return

    vsphere_host = creds["host"]
    vsphere_user = creds["username"]
    vsphere_password = creds["password"]

    service_instance = connect_vsphere(vsphere_host, vsphere_user, vsphere_password)
    content = service_instance.RetrieveContent()

    # Step 5: Read the generated VM configurations
    try:
        with open(output_file, "r") as f:
            vm_configs = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError) as e:
        print(f"Error reading VM config file: {e}")
        Disconnect(service_instance)
        return

    # Step 6: Clone VMs and collect statuses
    vm_statuses = []
    for vm_config in vm_configs:
        status = clone_vm(content, vm_config['SourceVM'], vm_config)
        vm_statuses.append(status)

    # Step 7: Disconnect from vSphere
    Disconnect(service_instance)

    # Step 8: Print the VM creation statuses
    print("\nSummary of VM Creation:")
    for status in vm_statuses:
        print(f"{status['NameVM']:<12} | {status['Status']:<10}")
    print("VM creation process complete.\n")

if __name__ == "__main__":
    main()
