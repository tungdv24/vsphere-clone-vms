import json

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
