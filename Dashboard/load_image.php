<?php
session_start();
date_default_timezone_set('Asia/Ho_Chi_Minh');
?>

<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Workdata</title>
    <!-- jQuery -->
    <script src="https://code.jquery.com/jquery-3.7.1.min.js"></script>
    <!-- DataTable -->
    <link rel="stylesheet"
        href="https://cdn.datatables.net/1.13.8/css/jquery.dataTables.min.css">
    <script src="https://cdn.datatables.net/1.13.8/js/jquery.dataTables.min.js"></script>
    <!-- Buttons -->
    <link rel="stylesheet"
        href="https://cdn.datatables.net/buttons/2.4.2/css/buttons.dataTables.min.css">
    <script src="https://cdn.datatables.net/buttons/2.4.2/js/dataTables.buttons.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/jszip/3.10.1/jszip.min.js"></script>
    <script src="https://cdn.datatables.net/buttons/2.4.2/js/buttons.html5.min.js"></script>
    <style>
        body {
            font-family: Arial, sans-serif;
            padding: 20px;
        }
        .toast-custom {
            position: fixed;
            top: 20px;
            right: 20px;
            background: #28a745;
            color: white;
            padding: 10px 20px;
            border-radius: 5px;
            z-index: 9999;
        }
        table.dataTable tbody tr {
            cursor: pointer;
        }
        th {
            text-align: center !important;
            white-space: nowrap;
            vertical-align: middle !important;
        }
        .product-image{ 
            width:80px; 
            height:80px; 
            object-fit:contain; 
            border:1px solid #ddd; 
            border-radius:5px; 
        }
    </style>
</head>

<body>
    <button id="Search">Load Data</button>
    <table id="tbl" class="display nowrap" style="width:100%">
        <thead id="tblHead"></thead>
        <tbody></tbody>
    </table>

    <script>
        let RAW = [];
        $(document).ready(function () {
            function updateTable() {

                $.ajax({
                    url: "Function/load_image.php",
                    type: "POST",
                    dataType: "json",
                    success: function (response) {
                        console.log(response);
                        if (response.success) {
                            RAW = response.data;
                            const toast = $('<div class="toast-custom">Loading Completed!</div>');
                            $('body').append(toast);
                            setTimeout(() => {
                                toast.fadeOut(200, function () {
                                    $(this).remove();
                                });
                            }, 1500);
                            renderTable(response);
                        }
                    },
                    error: function (xhr) {
                        console.log(xhr.responseText);
                        alert("Lỗi khi tải dữ liệu");
                    }
                });
            }

            $("#Search").click(function () {
                updateTable();
            });

            function renderTable(response) {
                let columns = response.column || [];
                let data = response.data || [];
                columns.forEach(col => {
                    if (col.data === 'img') {
                        col.render = function(data) {
                            return `<img src="${data}" class="product-image" width="80" height="80">`;
                        };
                    }
                });

                // destroy old table
                if ($.fn.DataTable.isDataTable("#tbl")) {
                    $('#tbl').DataTable().destroy();
                    $('#tbl tbody').empty();
                }
                // init datatable
                $('#tbl').DataTable({
                    data: data,
                    columns: columns,
                    scrollX: true,
                    scrollY: "500px",
                    scrollCollapse: true,
                    destroy: true,
                    autoWidth: false,
                    searching: true,
                    paging: true,
                    ordering: true,
                    info: true,
                    dom: 'Blfrtip',
                    buttons: [
                        {
                            extend: 'excelHtml5',
                            text: '📥 Excel'
                        },
                        {
                            extend: 'copyHtml5',
                            text: '📋 Copy'
                        }
                    ]
                });
            }            
        });
    </script>
</body>

</html>
