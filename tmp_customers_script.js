
let currentPage = 1;
let currentCustomerId = null;

var csrfToken = $('meta[name="csrf-token"]').attr('content');

$.ajaxSetup({
    headers: {
        'X-CSRFToken': csrfToken
    }
});


$(document).ready(function() {
    
    loadCustomerAnalytics();
    loadCustomers();

    // Search functionality
    $('#searchInput').on('keyup', function() {
        currentPage = 1;
        loadCustomers();
    });

    // Clear search
    $('#clearSearch').on('click', function() {
        $('#searchInput').val('');
        currentPage = 1;
        loadCustomers();
    });

    // Sort functionality
    $('#sortBy').on('change', function() {
        currentPage = 1;
        loadCustomers();
    });

    // Show inactive toggle - SIMPLE BUTTON with onclick handler
    console.log('jQuery setup for checkbox button starting...');
    
    window.showInactiveState = false;
    
    // Global function to toggle inactive
    window.toggleInactive = function() {
        console.log('🔴 TOGGLE INACTIVE CALLED');
        console.log('Current state:', window.showInactiveState);
        
        // Toggle state
        window.showInactiveState = !window.showInactiveState;
        console.log('New state:', window.showInactiveState);
        
        const btn = $('#inactiveCheckboxBtn');
        const box = $('#checkboxBox');
        
        if (window.showInactiveState) {
            // CHECKED - Turn blue
            btn.css({
                'background-color': '#d1ecf1',
                'border-color': '#0d6efd',
                'color': '#0d6efd',
                'font-weight': 'bold'
            });
            box.css({
                'background-color': '#0d6efd',
                'border-color': '#0d6efd',
                'color': 'white'
            }).html('✓');
            console.log('✓ CHECKED: Button turned BLUE');
        } else {
            // UNCHECKED - Turn gray
            btn.css({
                'background-color': '#f0f0f0',
                'border-color': '#999',
                'color': '#333',
                'font-weight': 'normal'
            });
            box.css({
                'background-color': 'white',
                'border-color': '#999',
                'color': '#333'
            }).html('');
            console.log('✓ UNCHECKED: Button turned GRAY');
        }
        
        // Load customers with new state
        currentPage = 1;
        loadCustomers();
    };
    
    console.log('✓ toggleInactive function ready');

    // Customer form submission - use event delegation for modal elements
    $(document).on('submit', '#customerForm', function(e) {
        e.preventDefault();
        saveCustomer();
    });

    // Also use event delegation for button click
    $(document).on('click', '#saveCustomerBtn', function(e) {
        console.log('Save customer button clicked');
    });
    
    // Bind customer order buttons
    bindCustomerOrderButtons();
    $(document).on('click', '[data-action="take-order"]', function(e) {
        e.preventDefault();
        const customerId = Number($(this).data('customer-id'));
        const customerName = $(this).data('customer-name') || '';
        console.log('Take Order action clicked', { customerId, customerName });
        if (customerId) {
            startTakeOrder(customerId, customerName);
        } else {
            console.warn('Take Order clicked with no customerId:', this);
        }
    });
    $(document).on('click', '[data-action="view-orders"]', function(e) {
        e.preventDefault();
        const customerId = Number($(this).data('customer-id'));
        const customerName = $(this).data('customer-name') || '';
        console.log('View Orders action clicked', { customerId, customerName });
        if (customerId) {
            openCustomerOrders(customerId, customerName);
        }
    });
});

function loadCustomerAnalytics() {
    $.get('/customers/api/customers/analytics')
        .done(function(data) {
            $('#totalCustomers').text(data.total_customers);
            $('#activeCustomers').text(data.active_customers);
            $('#avgOrderValue').text('₨ ' + parseFloat(data.average_order_value).toFixed(2));
            $('#totalRevenue').text('₨ ' + parseFloat(data.total_revenue).toFixed(2));
        })
        .fail(function() {
            console.error('Failed to load customer analytics');
        });
}

function loadCustomers() {
    const search = $('#searchInput').val();
    const sortBy = $('#sortBy').val();
    
    // Ensure state variable is initialized
    if (window.showInactiveState === undefined) {
        window.showInactiveState = false;
    }
    
    // Use the persistent state variable
    const showInactive = window.showInactiveState ? 'true' : 'false';

    $.get('/customers/api/customers', {
        page: currentPage,
        per_page: 50,
        search: search,
        sort_by: sortBy,
        show_inactive: showInactive
    })
    .done(function(data) {
        console.log('DEBUG: Received', data.customers.length, 'customers');
        console.log('DEBUG: Customer statuses:', data.customers.map(c => ({name: c.name, is_active: c.is_active})));
        renderCustomers(data.customers);
        renderPagination(data);
    })
    .fail(function() {
        showAlert('Error loading customers', 'danger');
    });
}

function renderCustomers(customers) {
    const $tbody = $('#customersTableBody');
    $tbody.empty();

    if (customers.length === 0) {
        $tbody.append('<tr><td colspan="7" class="text-center">No customers found</td></tr>');
        return;
    }

    customers.forEach(customer => {
        const creditStatus = getCreditStatus(customer);
        const lastPurchase = customer.last_purchase_date ?
            window.formatTimestamp(customer.last_purchase_date, false) : 'Never';
        
        // Add class for inactive customers
        const inactiveClass = customer.is_active ? '' : 'inactive-customer';
        const inactiveStyle = customer.is_active ? '' : 'style="background-color: #ff6666 !important; color: #660000 !important;"';
        const inactiveBadge = customer.is_active ? '' : '<span class="badge" style="background-color: #ff0000 !important; color: white !important; font-size: 12px; padding: 5px 10px; margin-left: 8px; font-weight: bold;">INACTIVE</span>';
        
        if (!customer.is_active) {
            console.log(`DEBUG: Adding inactive-customer class to ${customer.name}`);
        }

        const row = `
            <tr class="${inactiveClass}" ${inactiveStyle}>
                <td ${inactiveStyle}>
                    <strong style="${customer.is_active ? '' : 'color: #660000 !important;'}">${customer.name}</strong>
                    ${inactiveBadge}
                    ${customer.email ? `<br><small class="text-muted">${customer.email}</small>` : ''}
                </td>
                <td ${inactiveStyle}>
                    ${customer.phone || '-'}
                    ${customer.address ? `<br><small class="text-muted">${customer.address.substring(0, 30)}${customer.address.length > 30 ? '...' : ''}</small>` : ''}
                </td>
                <td ${inactiveStyle}>
                    <span class="badge loyalty-badge" style="color: #000 !important;">${customer.loyalty_points || 0}</span>
                </td>
                <td ${inactiveStyle}>₨ ${parseFloat(customer.total_purchases || 0).toFixed(2)}</td>
                <td ${inactiveStyle}>
                    <span class="credit-indicator ${creditStatus.class}"></span>
                    ₨ ${parseFloat(customer.current_balance || 0).toFixed(2)}
                    ${customer.credit_limit ? ` / ₨ ${parseFloat(customer.credit_limit).toFixed(2)}` : ''}
                </td>
                <td ${inactiveStyle}>${lastPurchase}</td>
                <td ${inactiveStyle}>
                    <div class="btn-group" role="group">
                        <button class="btn btn-sm btn-outline-info" onclick="viewCustomerDetails(${customer.id})" title="View Details">
                            <i class="fas fa-eye"></i>
                        </button>
                        <button class="btn btn-sm btn-outline-success" data-action="take-order" data-customer-id="${customer.id}" data-customer-name="${customer.name.replace(/'/g, "\\'")}" title="Take Order">
                            <i class="fas fa-cart-plus"></i>
                        </button>
                        ${customer.is_active ? `
                        <button class="btn btn-sm btn-outline-secondary" onclick="editCustomer(${customer.id})" title="Edit">
                            <i class="fas fa-edit"></i>
                        </button>
                        <button class="btn btn-sm btn-outline-danger" onclick="deleteCustomer(${customer.id}, '${customer.name}')" title="Archive">
                            <i class="fas fa-archive"></i>
                        </button>
                        ` : `
                        <button class="btn btn-sm btn-outline-success" onclick="restoreCustomer(${customer.id}, '${customer.name}')" title="Restore">
                            <i class="fas fa-trash-restore"></i>
                        </button>
                        `}
                    </div>
                </td>
            </tr>
        `;
        $tbody.append(row);
    });
    
    // Debug: Verify inactive class was applied
    const inactiveRows = $tbody.find('tr.inactive-customer').length;
    console.log('DEBUG: Found', inactiveRows, 'inactive customer rows');
}

function getCreditStatus(customer) {
    const balance = parseFloat(customer.current_balance || 0);
    const limit = parseFloat(customer.credit_limit || 0);

    if (balance === 0) return { class: 'credit-good' };
    if (limit > 0 && balance >= limit * 0.9) return { class: 'credit-danger' };
    if (limit > 0 && balance >= limit * 0.7) return { class: 'credit-warning' };
    return { class: 'credit-good' };
}

function renderPagination(data) {
    const $pagination = $('#pagination');
    $pagination.empty();

    if (data.pages <= 1) return;

    // Previous button
    if (data.current_page > 1) {
        $pagination.append(`<li class="page-item"><a class="page-link" href="#" onclick="changePage(${data.current_page - 1})">Previous</a></li>`);
    }

    // Page numbers
    for (let i = Math.max(1, data.current_page - 2); i <= Math.min(data.pages, data.current_page + 2); i++) {
        const activeClass = i === data.current_page ? 'active' : '';
        $pagination.append(`<li class="page-item ${activeClass}"><a class="page-link" href="#" onclick="changePage(${i})">${i}</a></li>`);
    }

    // Next button
    if (data.current_page < data.pages) {
        $pagination.append(`<li class="page-item"><a class="page-link" href="#" onclick="changePage(${data.current_page + 1})">Next</a></li>`);
    }
}

function changePage(page) {
    currentPage = page;
    loadCustomers();
}

function editCustomer(customerId) {
    $.get(`/customers/api/customers/${customerId}`)
        .done(function(customer) {
            currentCustomerId = customer.id;
            $('#customerModalTitle').text('Edit Customer');
            $('#customerName').val(customer.name);
            $('#customerPhone').val(customer.phone || '');
            $('#customerEmail').val(customer.email || '');
            $('#customerAddress').val(customer.address || '');
            $('#customerNotes').val(customer.notes || '');
            $('#customerPreferredPayment').val(customer.preferred_payment_method || '');
            $('#customerCreditLimit').val(customer.credit_limit || '');
            $('#customerCurrentBalance').val(customer.current_balance || '');

            $('#addCustomerModal').modal('show');
        })
        .fail(function() {
            showAlert('Error loading customer details', 'danger');
        });
}

function saveCustomer() {
    const customerData = {
        name: $('#customerName').val(),
        phone: $('#customerPhone').val(),
        email: $('#customerEmail').val(),
        address: $('#customerAddress').val(),
        notes: $('#customerNotes').val(),
        preferred_payment_method: $('#customerPreferredPayment').val(),
        credit_limit: $('#customerCreditLimit').val(),
        current_balance: $('#customerCurrentBalance').val()
    };

    // Validate name
    if (!customerData.name || customerData.name.trim() === '') {
        showAlert('Customer name is required', 'danger');
        return;
    }

    const url = currentCustomerId ? `/customers/api/customers/${currentCustomerId}` : '/customers/api/customers';
    const method = currentCustomerId ? 'PUT' : 'POST';

    $.ajax({
        url: url,
        method: method,
        contentType: 'application/json',
        headers: {
            'X-CSRFToken': csrfToken
        },
        data: JSON.stringify(customerData)
    })
    .done(function(response) {
        if (response.success) {
            $('#addCustomerModal').modal('hide');
            $('#customerForm')[0].reset();
            currentCustomerId = null;
            loadCustomers();
            loadCustomerAnalytics();
            showAlert(response.message, 'success');
        } else {
            showAlert(response.error || 'Error saving customer', 'danger');
        }
    })
    .fail(function(jqXHR) {
        // Handle the case when an archived customer with same name exists
        try {
            const response = JSON.parse(jqXHR.responseText);
            if (response.error && response.archived_customer_id) {
                // Show confirmation to restore the archived customer
                const customerName = $('#customerName').val();
                if (confirm(`A customer with name "${customerName}" already exists but is archived. Would you like to restore it?`)) {
                    restoreAndUpdateCustomer(response.archived_customer_id, customerData);
                }
            } else {
                showAlert(response.error || 'Error saving customer', 'danger');
            }
        } catch (e) {
            console.error('Error parsing response:', e);
            showAlert('Error saving customer: ' + jqXHR.status + ' ' + jqXHR.statusText, 'danger');
        }
    });
}

function restoreAndUpdateCustomer(archivedCustomerId, customerData) {
    // First restore the customer
    $.ajax({
        url: `/customers/api/customers/${archivedCustomerId}/restore`,
        method: 'POST',
        headers: {
            'X-CSRFToken': csrfToken
        }
    })
    .done(function(response) {
        if (response.success) {
            // Then update with the new data
            $.ajax({
                url: `/customers/api/customers/${archivedCustomerId}`,
                method: 'PUT',
                contentType: 'application/json',
                headers: {
                    'X-CSRFToken': csrfToken
                },
                data: JSON.stringify(customerData)
            })
            .done(function(updateResponse) {
                if (updateResponse.success) {
                    $('#addCustomerModal').modal('hide');
                    $('#customerForm')[0].reset();
                    currentCustomerId = null;
                    loadCustomers();
                    loadCustomerAnalytics();
                    showAlert('Customer restored and updated successfully!', 'success');
                } else {
                    showAlert(updateResponse.error || 'Error updating customer', 'danger');
                }
            })
            .fail(function() {
                showAlert('Error updating customer', 'danger');
            });
        } else {
            showAlert(response.error || 'Error restoring customer', 'danger');
        }
    })
    .fail(function() {
        showAlert('Error restoring customer', 'danger');
    });
}

function deleteCustomer(customerId, customerName) {
    if (confirm(`Are you sure you want to archive "${customerName}"? The customer data will be preserved and can be restored later.`)) {
        $.ajax({
            url: `/customers/api/customers/${customerId}`,
            method: 'DELETE'
        })
        .done(function(response) {
            if (response.success) {
                loadCustomers();
                loadCustomerAnalytics();
                showAlert(response.message, 'success');
            } else {
                showAlert(response.error || 'Error archiving customer', 'danger');
            }
        })
        .fail(function() {
            showAlert('Error archiving customer', 'danger');
        });
    }
}

function restoreCustomer(customerId, customerName) {
    if (confirm(`Are you sure you want to restore "${customerName}"?`)) {
        $.ajax({
            url: `/customers/api/customers/${customerId}/restore`,
            method: 'POST'
        })
        .done(function(response) {
            if (response.success) {
                loadCustomers();
                loadCustomerAnalytics();
                showAlert(response.message, 'success');
            } else {
                showAlert(response.error || 'Error restoring customer', 'danger');
            }
        })
        .fail(function() {
            showAlert('Error restoring customer', 'danger');
        });
    }
}

function viewCustomerDetails(customerId) {
    currentCustomerId = customerId;

    // Load customer info
    $.get(`/customers/api/customers/${customerId}`)
        .done(function(customer) {
            const infoHtml = `
                <p><strong>Name:</strong> ${customer.name}</p>
                <p><strong>Phone:</strong> ${customer.phone || '-'}</p>
                <p><strong>Email:</strong> ${customer.email || '-'}</p>
                <p><strong>Address:</strong> ${customer.address || '-'}</p>
                <p><strong>Total Purchases:</strong> ₨ ${parseFloat(customer.total_purchases || 0).toFixed(2)}</p>
                <p><strong>Credit Limit:</strong> ₨ ${parseFloat(customer.credit_limit || 0).toFixed(2)}</p>
                <p><strong>Current Balance:</strong> ₨ ${parseFloat(customer.current_balance || 0).toFixed(2)}</p>
                <p><strong>Registration Date:</strong> ${customer.registration_date || '-'}</p>
                <p><strong>Notes:</strong> ${customer.notes || '-'}</p>
            `;
            $('#customerInfo').html(infoHtml);
            $('#loyaltyPoints').text(customer.loyalty_points || 0);
        });

    // Load purchase history
    $.get(`/customers/api/customers/${customerId}/purchase-history`)
        .done(function(data) {
            const $tbody = $('#purchaseHistoryTableBody');
            $tbody.empty();

            if (data.sales.length === 0) {
                $tbody.append('<tr><td colspan="4" class="text-center">No purchase history found</td></tr>');
            } else {
                data.sales.forEach(sale => {
                    const itemsText = sale.items.map(item => `${item.product_name} (${item.quantity})`).join(', ');
                    const row = `
                        <tr>
                            <td>${window.formatTimestamp(sale.date, true)}</td>
                            <td><small>${itemsText}</small></td>
                            <td>₨ ${parseFloat(sale.total).toFixed(2)}</td>
                            <td>${sale.payment}</td>
                        </tr>
                    `;
                    $tbody.append(row);
                });
            }
        });

    $('#customerDetailsModal').modal('show');
    bindCustomerOrderButtons();
}

function bindCustomerOrderButtons() {
    $('#viewCustomerOrdersBtn').off('click').on('click', function() {
        const customerId = currentCustomerId;
        const customerName = $('#customerInfo').text().match(/Name:\\s*(.*?)(?:\\n|$)/)?.[1] || '';
        openCustomerOrders(customerId, customerName.trim());
    });

    $('#takeOrderBtn').off('click').on('click', function() {
        const customerId = currentCustomerId;
        const customerName = $('#customerInfo').text().match(/Name:\\s*(.*?)(?:\\n|$)/)?.[1] || '';
        openTakeOrderModal(customerId, customerName.trim());
    });
}

function adjustLoyaltyPoints(points) {
    if (!currentCustomerId) return;

    $.ajax({
        url: `/customers/api/customers/${currentCustomerId}/loyalty`,
        method: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({ points: points })
    })
    .done(function(response) {
        if (response.success) {
            $('#loyaltyPoints').text(response.new_points);
            loadCustomers(); // Refresh the table
            showAlert(`Loyalty points updated to ${response.new_points}`, 'success');
        } else {
            showAlert(response.error || 'Error updating loyalty points', 'danger');
        }
    })
    .fail(function() {
        showAlert('Error updating loyalty points', 'danger');
    });
}

function showAlert(message, type) {
    const alertHtml = `
        <div class="alert alert-${type} alert-dismissible fade show">
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        </div>
    `;
    $('.container-fluid').prepend(alertHtml);
    setTimeout(() => $('.alert').fadeOut(), 5000);
}

// Reset modal when closed
$('#addCustomerModal').on('hidden.bs.modal', function() {
    $('#customerForm')[0].reset();
    currentCustomerId = null;
    $('#customerModalTitle').text('Add New Customer');
});

// Outstanding Aging Functions
$('#outstanding-tab').on('click', function() {
    loadOutstandingAging();
});

function loadOutstandingAging() {
    $.get('/customers/api/customers/outstanding-aging')
        .done(function(data) {
            // Update summary cards
            $('#outstanding0_30').text('₨ ' + parseFloat(data.totals['0_30_days'].total).toFixed(2));
            $('#count0_30').text(data.totals['0_30_days'].count + ' customers');
            
            $('#outstanding30_60').text('₨ ' + parseFloat(data.totals['30_60_days'].total).toFixed(2));
            $('#count30_60').text(data.totals['30_60_days'].count + ' customers');
            
            $('#outstanding60_90').text('₨ ' + parseFloat(data.totals['60_90_days'].total).toFixed(2));
            $('#count60_90').text(data.totals['60_90_days'].count + ' customers');
            
            $('#outstanding90_plus').text('₨ ' + parseFloat(data.totals['90_plus_days'].total).toFixed(2));
            $('#count90_plus').text(data.totals['90_plus_days'].count + ' customers');
            
            // Render customers table
            renderOutstandingCustomers(data.customers);
        })
        .fail(function() {
            showAlert('Error loading outstanding aging data', 'danger');
        });
}

function renderOutstandingCustomers(customers) {
    const $tbody = $('#outstandingTableBody');
    $tbody.empty();

    if (customers.length === 0) {
        $tbody.append('<tr><td colspan="10" class="text-center">No customers with outstanding balance</td></tr>');
        return;
    }

    customers.forEach(customer => {
        const rowClass = customer.supply_stopped ? 'supply-stopped' : '';
        const statusBadge = customer.supply_stopped 
            ? '<span class="supply-stopped-badge">Supply Stopped</span>' 
            : '<span class="badge bg-success">Active</span>';
        
        const row = `
            <tr class="${rowClass}">
                <td>
                    <strong>${customer.name}</strong>
                </td>
                <td>${customer.phone || '-'}</td>
                <td class="text-success">₨ ${parseFloat(customer.outstanding_0_30 || 0).toFixed(2)}</td>
                <td class="text-info">₨ ${parseFloat(customer.outstanding_30_60 || 0).toFixed(2)}</td>
                <td class="text-warning">₨ ${parseFloat(customer.outstanding_60_90 || 0).toFixed(2)}</td>
                <td class="text-danger">₨ ${parseFloat(customer.outstanding_90_plus || 0).toFixed(2)}</td>
                <td><strong>₨ ${parseFloat(customer.total_outstanding || 0).toFixed(2)}</strong></td>
                <td>${statusBadge}</td>
                <td>
                    <div class="btn-group" role="group">
                        <button class="btn btn-sm btn-outline-info" onclick="viewCustomerDetails(${customer.id})" title="View Details">
                            <i class="fas fa-eye"></i>
                        </button>
                        ${customer.total_outstanding > 0 ? `
                        <button class="btn btn-sm btn-success" onclick="openPaymentModal(${customer.id}, '${customer.name.replace(/'/g, "\\'")}', ${customer.total_outstanding})" title="Record Payment">
                            <i class="fas fa-money-bill-wave"></i>
                        </button>
                        ` : ''}
                        ${customer.supply_stopped ? `
                        <button class="btn btn-sm btn-outline-success" onclick="toggleSupply(${customer.id}, false)" title="Resume Supply">
                            <i class="fas fa-play"></i>
                        </button>
                        ` : `
                        <button class="btn btn-sm btn-outline-danger" onclick="toggleSupply(${customer.id}, true)" title="Stop Supply">
                            <i class="fas fa-ban"></i>
                        </button>
                        `}
                    </div>
                </td>
            </tr>
        `;
        $tbody.append(row);
    });
}

function recalculateBalances() {
    if (!confirm('This will recalculate all customer balances based on their credit sales. Continue?')) {
        return;
    }
    
    $.ajax({
        url: '/customers/api/customers/recalculate-balance',
        method: 'POST',
        headers: {
            'X-CSRFToken': csrfToken
        }
    })
    .done(function(response) {
        if (response.success) {
            showAlert(response.message, 'success');
            loadOutstandingAging();
        } else {
            showAlert(response.error || 'Error recalculating balances', 'danger');
        }
    })
    .fail(function() {
        showAlert('Error recalculating balances', 'danger');
    });
}

function toggleSupply(customerId, stop) {
    const action = stop ? 'stop' : 'resume';
    if (!confirm(`Are you sure you want to ${action} supply for this customer?`)) {
        return;
    }
    
    $.ajax({
        url: `/customers/api/customers/${customerId}/stop-supply`,
        method: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({ stop: stop }),
        headers: {
            'X-CSRFToken': csrfToken
        }
    })
    .done(function(response) {
        if (response.success) {
            showAlert(response.message, 'success');
            loadOutstandingAging();
        } else {
            showAlert(response.error || 'Error updating supply status', 'danger');
        }
    })
    .fail(function() {
        showAlert('Error updating supply status', 'danger');
    });
}

// Payment Recording Functions
// Payment Recording - Use event delegation for modal buttons
document.addEventListener('DOMContentLoaded', function() {
    console.log('Payment handler setup starting...');
    // Setup cheque field toggle for payment modal
    function toggleChequeFieldsCustomer() {
        try {
            var pm = document.getElementById('paymentMethod');
            var chequeDiv = document.getElementById('paymentChequeDetails');
            if (!chequeDiv) return;
            var val = pm && pm.value ? pm.value : null;
            console.log('toggleChequeFieldsCustomer called, paymentMethod=', val);
            if (val && val.toLowerCase() === 'cheque') {
                chequeDiv.classList.remove('d-none');
                chequeDiv.classList.add('d-block');
                var cn = document.getElementById('chequeNumber');
                var pref = document.getElementById('paymentReference');
                if (cn && (!cn.value || cn.value.trim() === '') && pref && pref.value) cn.value = pref.value;
            } else {
                chequeDiv.classList.remove('d-block');
                chequeDiv.classList.add('d-none');
            }
        } catch (e) { console.error('toggleChequeFieldsCustomer error', e); }
    }
    // Attach listeners
    var pmElCust = document.getElementById('paymentMethod');
    if (pmElCust) {
        pmElCust.addEventListener('change', toggleChequeFieldsCustomer);
        pmElCust.addEventListener('input', toggleChequeFieldsCustomer);
    }
    document.addEventListener('change', function(e){ if (e.target && e.target.id === 'paymentMethod') toggleChequeFieldsCustomer(); });
    try { window.toggleChequeFieldsCustomer = toggleChequeFieldsCustomer; } catch(e) {}
    
    // Use event delegation on document level for modal button
    document.addEventListener('click', function(e) {
        // Check if the clicked element is the save payment button
        if (e.target.id === 'savePaymentBtn' || e.target.closest('#savePaymentBtn')) {
            console.log('==== BUTTON CLICK FIRED (via delegation) ====');
            e.preventDefault();
            e.stopPropagation();
            
            const customerId = document.getElementById('paymentCustomerId').value;
            const amount = document.getElementById('paymentAmount').value;
            const paymentMethod = document.getElementById('paymentMethod').value;
            const reference = document.getElementById('paymentReference').value;
            const notes = document.getElementById('paymentNotes').value;
            
            console.log('Form values:', {
                customerId: customerId,
                amount: amount,
                paymentMethod: paymentMethod,
                reference: reference,
                notes: notes
            });
            
            const amountFloat = parseFloat(amount);
            console.log('Parsed amount:', amountFloat);
            
            if (!customerId) {
                console.error('Customer ID is missing!');
                showAlert('Customer ID is missing', 'danger');
                return;
            }
            
            if (!amountFloat || amountFloat <= 0) {
                console.error('Invalid amount:', amountFloat);
                showAlert('Please enter a valid payment amount', 'danger');
                return;
            }
            
            console.log('Validation passed, submitting...');
            const savePaymentBtn = document.getElementById('savePaymentBtn');
            if (savePaymentBtn) {
                savePaymentBtn.disabled = true;
                savePaymentBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Saving...';
            }
            
            const paymentUrl = '/customers/api/customers/' + customerId + '/record-payment';
            console.log('POST URL:', paymentUrl);
            
            const csrfTokenElement = document.querySelector('meta[name="csrf-token"]');
            const csrfToken = csrfTokenElement ? csrfTokenElement.content : '';
            console.log('CSRF Token present:', csrfToken ? 'YES (' + csrfToken.substring(0, 10) + '...)' : 'NO');
            
            const requestBody = {
                amount: amountFloat,
                payment_method: paymentMethod,
                reference_number: reference,
                notes: notes
            };
            // Include cheque details if payment method is Cheque
            if (paymentMethod && paymentMethod.toLowerCase() === 'cheque') {
                requestBody.cheque_number = (document.getElementById('chequeNumber') && document.getElementById('chequeNumber').value) || reference;
                requestBody.cheque_bank = (document.getElementById('bankName') && document.getElementById('bankName').value) || '';
                requestBody.cheque_date = (document.getElementById('chequeDate') && document.getElementById('chequeDate').value) || '';
            }
            console.log('Request body:', requestBody);
            
            fetch(paymentUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken
                },
                body: JSON.stringify(requestBody)
            })
            .then(response => {
                console.log('==== FETCH RESPONSE RECEIVED ====');
                console.log('Status:', response.status, response.statusText);
                console.log('Content-Type:', response.headers.get('content-type'));
                
                if (!response.ok) {
                    console.error('HTTP Error:', response.status);
                    if (response.status === 403) {
                        return response.json().then(data => {
                            console.error('Permission denied (403):', data);
                            showAlert('Permission denied: You do not have permission to record payments', 'danger');
                            throw new Error('Permission denied');
                        });
                    } else if (response.status === 404) {
                        console.error('Not found (404)');
                        showAlert('Customer not found', 'danger');
                        throw new Error('Customer not found');
                    } else if (response.status >= 500) {
                        console.error('Server error (' + response.status + ')');
                        showAlert('Server error while recording payment. Status: ' + response.status, 'danger');
                        throw new Error('Server error');
                    }
                }
                console.log('Response OK, parsing JSON...');
                return response.json();
            })
            .then(data => {
                console.log('==== JSON PARSED SUCCESSFULLY ====');
                console.log('Response data:', data);
                if (data.success) {
                    console.log('SUCCESS! Recording payment completed');
                    showAlert('Payment recorded successfully! New balance: ₨' + data.new_balance.toFixed(2), 'success');
                    // Properly close Bootstrap modal
                    const modalElement = document.getElementById('paymentModal');
                    if (modalElement) {
                        console.log('Closing payment modal...');
                        const bsModal = bootstrap.Modal.getInstance(modalElement) || new bootstrap.Modal(modalElement);
                        bsModal.hide();
                    }
                    // Refresh data
                    setTimeout(function() {
                        console.log('Refreshing data...');
                        try { 
                            if (typeof loadOutstandingAging === 'function') loadOutstandingAging();
                            if (typeof loadCustomers === 'function') loadCustomers();
                            if (typeof loadCustomerAnalytics === 'function') loadCustomerAnalytics();
                        } catch(e) { console.error('Refresh error:', e); }
                    }, 500);
                } else if (data.error) {
                    console.error('API returned error:', data.error);
                    showAlert('Error: ' + data.error, 'danger');
                } else {
                    console.error('Unexpected response format:', data);
                    showAlert('Unexpected response from server', 'danger');
                }
            })
            .catch(error => {
                console.error('==== FETCH ERROR CAUGHT ====');
                console.error('Error message:', error.message);
                               console.error('Error stack:', error.stack);
                if (error.message !== 'Permission denied' && error.message !== 'Customer not found' && error.message !== 'Server error') {
                    showAlert('Error recording payment: ' + error.message, 'danger');
                }
            })
            .finally(() => {
                console.log('==== PAYMENT REQUEST COMPLETED ====');
                const savePaymentBtn = document.getElementById('savePaymentBtn');
                if (savePaymentBtn) {
                    savePaymentBtn.disabled = false;
                    savePaymentBtn.innerHTML = 'Record Payment';
                }
            });
        }
    }, true); // Use capture phase to catch all clicks
    
    console.log('Payment event delegation setup complete');
});

function openPaymentModal(customerId, customerName, outstandingBalance) {
    $('#paymentCustomerId').val(customerId);
    $('#paymentCustomerName').val(customerName);
    $('#paymentOutstandingBalance').val('₨ ' + outstandingBalance.toFixed(2));
    $('#paymentAmount').val(outstandingBalance.toFixed(2));
    $('#paymentReference').val('');
    $('#paymentNotes').val('');
    
    $('#paymentModal').modal('show');
}

$(document).ready(function() {
    // Orders tab functionality
    console.log('Orders tab handlers attaching');
    $('#orders-tab').on('click', function() {
        loadOrders();
    });

    $('#refreshOrdersBtn').on('click', function() { loadOrders(); });
    $('#takeOrderFromOrdersBtn').on('click', function() {
        console.log('Orders tab Take Order button clicked, currentCustomerId=', currentCustomerId);
        let customerId = currentCustomerId || null;
        let customerName = '';
        const filterVal = $('#ordersCustomerSearch').val() || '';
        const firstCustomerRow = $('#customersTableBody tr').first();

        if (customerId) {
            customerName = $('#customerInfo').text().match(/Name:\s*(.*?)(?:\n|$)/)?.[1] || '';
        }

        if (!customerId && firstCustomerRow.length) {
            const firstId = firstCustomerRow.find('[data-action="take-order"]').data('customer-id');
            if (firstId) customerId = Number(firstId);
            const firstName = firstCustomerRow.find('td strong').first().text().trim();
            if (firstName) customerName = firstName;
        }

        if (!customerId && filterVal) {
            const matchRow = $('#customersTableBody tr').filter(function() {
                return $(this).find('td strong').first().text().toLowerCase().includes(filterVal.toLowerCase());
            }).first();
            if (matchRow.length) {
                customerId = Number(matchRow.find('[data-action="take-order"]').data('customer-id'));
                customerName = matchRow.find('td strong').first().text().trim();
            }
        }

        if (!customerId) {
            showAlert('Open a customer from the customer list first, then use the Take Order button in the customer details or customer row.', 'warning');
            return;
        }

        startTakeOrder(customerId, customerName.trim());
    });

    $('#ordersCustomerSearch').on('keyup', function() { loadOrders(); });
});

function loadOrders(page = 1) {
    const customerName = $('#ordersCustomerSearch').val();
    $.get('/customers/api/orders', { page: page, per_page: 50, customer_name: customerName })
        .done(function(data) {
            renderOrders(data.orders);
        })
        .fail(function() { showAlert('Error loading orders', 'danger'); });
}

function renderOrders(orders) {
    const $tbody = $('#ordersTableBody');
    $tbody.empty();
    if (!orders || orders.length === 0) {
        $tbody.append('<tr><td colspan="8" class="text-center text-muted py-4">No orders found for this customer yet.<br><small>Open a customer and click <strong>Take Order</strong> to create one.</small></td></tr>');
        return;
    }
    orders.forEach(o => {
        const itemsText = o.items.map(i => `${i.product_name} (${i.quantity})`).join(', ');
        const row = `
            <tr>
                <td>${o.id}</td>
                <td>${o.date}</td>
                <td>${o.customer}</td>
                <td><small>${itemsText}</small></td>
                <td>₨ ${parseFloat(o.total || 0).toFixed(2)}</td>
                <td>${o.payment}</td>
                <td>₨ ${parseFloat(o.balance || 0).toFixed(2)}</td>
                <td>
                    <div class="btn-group">
                        <button class="btn btn-sm btn-outline-info" onclick="openEditOrderModal(${o.id})">Edit</button>
                    </div>
                </td>
            </tr>
        `;
        $tbody.append(row);
    });
}

function openEditOrderModal(orderId) {
    // Load order details
    fetch('/customers/api/orders?per_page=1')
        .then(() => {
            // We don't have single-order GET, so populate fields from table row
            const $row = $(`#ordersTableBody tr`).filter(function() { return $(this).find('td:first').text() == orderId; }).first();
            if ($row.length === 0) {
                showAlert('Order not found in table', 'danger');
                return;
            }
            const totalText = $row.find('td').eq(4).text().replace('₨', '').trim();
            const payment = $row.find('td').eq(5).text().trim();
            const balanceText = $row.find('td').eq(6).text().replace('₨', '').trim();

            $('#editOrderId').val(orderId);
            $('#editOrderPayment').val(payment);
            $('#editOrderTotal').val(parseFloat(totalText) || 0);
            $('#editOrderBalance').val(parseFloat(balanceText) || 0);

            $('#editOrderModal').modal('show');
        })
        .catch(() => showAlert('Error opening order', 'danger'));
}

$('#saveOrderBtn').on('click', function() {
    const orderId = $('#editOrderId').val();
    const payload = {
        payment: $('#editOrderPayment').val(),
        total: parseFloat($('#editOrderTotal').val()) || 0,
        balance: parseFloat($('#editOrderBalance').val()) || 0
    };

    fetch('/customers/api/orders/' + orderId, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
        body: JSON.stringify(payload)
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {

            $('#editOrderModal').modal('hide');
            showAlert(data.message || 'Order updated', 'success');
            loadOrders();
        } else {
            showAlert(data.error || 'Error updating order', 'danger');
        }
    })
    .catch(() => showAlert('Error updating order', 'danger'));
});

function openCustomerOrders(customerId, customerName) {
    const ordersTabEl = document.querySelector('#orders-tab');
    if (ordersTabEl) {
        const tab = bootstrap.Tab.getOrCreateInstance(ordersTabEl);
        tab.show();
    }
    $('#ordersCustomerSearch').val(customerName || '');
    loadOrders(1);
}

function startTakeOrder(customerId, customerName) {
    openTakeOrderModal(customerId, customerName);
}

let takeOrderItems = [];

function openTakeOrderModal(customerId, customerName) {
    console.log('openTakeOrderModal called', { customerId, customerName });
    if (!customerId) {
        showAlert('Unable to open order form: missing customer ID.', 'danger');
        return;
    }
    currentCustomerId = customerId;
    $('#takeOrderCustomerName').val(customerName || '');
    $('#takeOrderDate').val(new Date().toISOString().slice(0, 10));
    $('#takeOrderProductSearch').val('');
    $('#takeOrderPaymentMethod').val('Cash');
    $('#takeOrderNotes').val('');
    $('#takeOrderProductResults').html('');
    takeOrderItems = [];
    updateTakeOrderItemsTable();
    toggleTakeOrderChequeFields();
    $('#takeOrderModal').modal('show');
    loadTakeOrderProducts();
}

function loadTakeOrderProducts() {
    const search = $('#takeOrderProductSearch').val() || '';
    const url = `/customers/api/products/search?search=${encodeURIComponent(search)}`;
    console.log('Searching products with URL:', url);
    fetch(url)
        .then(res => {
            if (!res.ok) {
                return res.text().then(text => {
                    console.error('Product search failed', res.status, text);
                    throw new Error('Product search failed: ' + res.status);
                });
            }
            return res.json();
        })
        .then(products => {
            const results = $('#takeOrderProductResults');
            results.empty();
            if (!products || products.length === 0) {
                results.html('<div class="text-muted">No products found</div>');
                return;
            }
            products.slice(0, 20).forEach(product => {
                const item = document.createElement('div');
                item.className = 'd-flex justify-content-between align-items-center border rounded p-2 mb-2 bg-white';
                item.innerHTML = `
                    <div>
                        <strong>${product.name}</strong><br>
                        <small class="text-muted">Stock: ${product.stock} | Price: ₨ ${parseFloat(product.price || 0).toFixed(2)}</small>
                    </div>
                    <button class="btn btn-sm btn-success" type="button" data-product-id="${product.id}" data-product-name="${product.name}" data-product-price="${product.price || 0}">Add</button>
                `;
                results.append(item);
            });
            results.find('button').off('click').on('click', function() {
                const productId = Number($(this).data('product-id'));
                const productName = $(this).data('product-name');
                const productPrice = Number($(this).data('product-price')) || 0;
                addTakeOrderItem(productId, productName, productPrice);
            });
        })
        .catch(() => {
            $('#takeOrderProductResults').html('<div class="text-danger">Unable to load products</div>');
        });
}

function addTakeOrderItem(productId, productName, productPrice) {
    const existing = takeOrderItems.find(item => item.product_id === productId);
    if (existing) {
        existing.quantity += 1;
    } else {
        takeOrderItems.push({
            product_id: productId,
            product_name: productName,
            quantity: 1,
            price: productPrice
        });
    }
    updateTakeOrderItemsTable();
}

function updateTakeOrderItemsTable() {
    const body = $('#takeOrderItemsTableBody');
    body.empty();

    if (takeOrderItems.length === 0) {
        body.html('<tr><td colspan="5" class="text-center text-muted">No products added</td></tr>');
        $('#takeOrderTotal').val('0.00');
        return;
    }

    let total = 0;
    takeOrderItems.forEach((item, index) => {
        const lineTotal = item.quantity * item.price;
        total += lineTotal;
        body.append(`
            <tr>
                <td>${item.product_name}</td>
                <td>
                    <input type="number" class="form-control form-control-sm" min="1" value="${item.quantity}" data-index="${index}" data-role="qty">
                </td>
                <td>₨ ${parseFloat(item.price || 0).toFixed(2)}</td>
                <td>₨ ${parseFloat(lineTotal).toFixed(2)}</td>
                <td><button class="btn btn-sm btn-outline-danger" type="button" data-index="${index}" data-role="remove-item">Remove</button></td>
            </tr>
        `);
    });

    $('#takeOrderTotal').val(parseFloat(total).toFixed(2));

    body.find('[data-role="qty"]').off('change').on('change', function() {
        const idx = Number($(this).data('index'));
        const qty = Number($(this).val()) || 0;
        if (qty <= 0) {
            takeOrderItems.splice(idx, 1);
        } else {
            takeOrderItems[idx].quantity = qty;
        }
        updateTakeOrderItemsTable();
    });

    body.find('[data-role="remove-item"]').off('click').on('click', function() {
        const idx = Number($(this).data('index'));
        takeOrderItems.splice(idx, 1);
        updateTakeOrderItemsTable();
    });
}

function toggleTakeOrderChequeFields() {
    const method = $('#takeOrderPaymentMethod').val();
    const detailDiv = $('#takeOrderChequeDetails');
    if (method && method.toLowerCase() === 'cheque') {
        detailDiv.removeClass('d-none');
    } else {
        detailDiv.addClass('d-none');
    }
}

$(document).ready(function() {
    $('#loadTakeOrderProductsBtn').on('click', function() { loadTakeOrderProducts(); });
    $('#takeOrderProductSearch').on('keyup', function(e) {
        if (e.key === 'Enter') loadTakeOrderProducts();
    });
    $('#takeOrderPaymentMethod').on('change', toggleTakeOrderChequeFields);

    $('#submitTakeOrderBtn').on('click', function() {
        if (!currentCustomerId) {
            showAlert('Please select a customer first', 'danger');
            return;
        }
    if (takeOrderItems.length === 0) {
        showAlert('Please add at least one product to the order', 'danger');
        return;
    }

    const paymentMethod = $('#takeOrderPaymentMethod').val();
    const chequeNumber = $('#takeOrderChequeNumber').val();
    const bankName = $('#takeOrderBankName').val();
    const chequeDate = $('#takeOrderChequeDate').val();

    if (paymentMethod === 'Cheque' && (!chequeNumber || !bankName || !chequeDate)) {
        showAlert('Cheque number, bank name, and date are required for cheque payments', 'danger');
        return;
    }

    const payload = {
        customer_id: currentCustomerId,
        customer_name: $('#takeOrderCustomerName').val(),
        payment_method: paymentMethod,
        total: parseFloat($('#takeOrderTotal').val() || 0),
        balance: 0,
        notes: $('#takeOrderNotes').val() || '',
        cheque_number: chequeNumber || '',
        cheque_bank: bankName || '',
        cheque_date: chequeDate || '',
        items: takeOrderItems.map(item => ({
            product_id: item.product_id,
            product_name: item.product_name,
            quantity: Number(item.quantity),
            price: Number(item.price)
        }))
    };

    fetch('/customers/api/orders', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfToken
        },
        body: JSON.stringify(payload)
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            $('#takeOrderModal').modal('hide');
            showAlert(data.message || 'Order created successfully', 'success');
            loadOrders();
        } else {
            showAlert(data.error || 'Error creating order', 'danger');
        }
    })
    .catch(() => showAlert('Error creating order', 'danger'));
});
});
