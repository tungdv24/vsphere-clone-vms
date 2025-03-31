$(document).ready(function () {
    let isAuthenticated = false;

    function showAlert(message, type = "info") {
        const alertId = `alert-${Date.now()}`;
        const alertHtml = `
            <div id="${alertId}" class="alert alert-${type} alert-dismissible fade show mb-2" role="alert">
                ${message}
                <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
            </div>`;
        $('#alertBox').append(alertHtml);
        setTimeout(() => { $(`#${alertId}`).alert('close'); }, 5000);
    }

    function requireAuth(callback) {
        if (isAuthenticated) {
            callback();
        } else {
            $('#authModal').modal('show');
            $('#verifyTotpButton').off('click').click(() => {
                const code = $('#totpCode').val();
                if (!code) return;

                $.ajax({
                    url: '/verify_totp',
                    type: 'POST',
                    contentType: 'application/json',
                    data: JSON.stringify({ code }),
                    success: function () {
                        isAuthenticated = true;
                        $('#authModal').modal('hide');
                        callback();
                    },
                    error: function () {
                        $('#totpError').show();
                        setTimeout(() => { $('#totpError').hide(); }, 3000);
                    }
                });
            });
        }
    }

    function refreshVMTable() {
        $.get('/get_configured_vms', function (data) {
            const tableBody = $('#vmTable tbody');
            tableBody.empty();
            data.forEach((vm, index) => {
                tableBody.append(`
                    <tr>
                        <td>${vm.NameVM}</td>
                        <td>${vm.Count}</td>
                        <td>${vm.CPU}/${vm.RAM}/${vm.Disk}</td>
                        <td>${vm.IPList.join(', ')}</td>
                        <td>
                            <button class="btn btn-danger btn-sm remove-vm" data-index="${index}">Remove</button>
                        </td>
                    </tr>
                `);
            });

            $('.remove-vm').click(function () {
                const vmIndex = $(this).data('index');
                requireAuth(() => {
                    $.post(`/remove_vm/${vmIndex}`, function (response) {
                        showAlert(response.message, "success");
                        refreshVMTable();
                    }).fail(function () {
                        showAlert('Failed to remove VM.', "danger");
                    });
                });
            });
        });
    }

    function refreshFinalizedVMTable() {
        $.get('/get_finalized_vms', function (data) {
            const tableBody = $('#finalizedSpecsTable');
            tableBody.empty();
            data.forEach((vm) => {
                tableBody.append(`
                    <tr>
                        <td>${vm.NameVM}</td>
                        <td>${vm.CPU}/${vm.RAM}/${vm.Disk}</td>
                        <td>${vm.Network}</td>
                        <td>${vm.IP}</td>
                    </tr>
                `);
            });
        });
    }

    $('#addVM').click(function () {
        requireAuth(() => {
            const formData = $('#vmForm').serialize();
            $.post('/submit', formData, function (response) {
                showAlert(response.message, "success");
                refreshVMTable();
            }).fail(function () {
                showAlert('Failed to add VM.', "danger");
            });
        });
    });

    $('#finalizeButton').click(function () {
        requireAuth(() => {
            $.post('/finalize', function (response) {
                showAlert(response.message, "success");
                refreshFinalizedVMTable();
                $('#finalizedSpecsSection').show();
                $('#runButton').show();
            }).fail(function () {
                showAlert('Failed to finalize VMs.', "danger");
            });
        });
    });

    $('#runButton').click(function () {
        requireAuth(() => {
            if (confirm('Are you sure you want to run the creation process?')) {
                $.post('/create', function (response) {
                    if (response.message) showAlert(response.message, "success");
                    if (response.output) {
                        response.output.split('\n').forEach((log) => {
                            if (log.trim()) showAlert(log, "info");
                        });
                    }
                }).fail(function () {
                    showAlert('An error occurred while running the process.', "danger");
                });
            }
        });
    });

    $('#deleteAllButton').click(function () {
        requireAuth(() => {
            $.post('/clear_all', function (response) {
                showAlert(response.message, "success");
                refreshVMTable();
                $('#finalizedSpecsTable').empty();
                $('#finalizedSpecsSection').hide();
                $('#runButton').hide();
            }).fail(function () {
                showAlert('Failed to clear configurations.', "danger");
            });
        });
    });

    refreshVMTable();
    refreshFinalizedVMTable();
});
