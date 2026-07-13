// Base JavaScript for POS Web Application

// Global toggle function for sidebar (direct onclick handler)
function toggleSidebar(event) {
    event.preventDefault();
    event.stopPropagation();
    const sidebar = document.getElementById('sidebar');
    const sidebarOverlay = document.getElementById('sidebarOverlay');
    
    if (sidebar) {
        sidebar.classList.toggle('open');
        if (sidebarOverlay) {
            sidebarOverlay.classList.toggle('active');
        }
        if (sidebar.classList.contains('open')) {
            document.body.style.overflow = 'hidden';
        } else {
            document.body.style.overflow = '';
        }
    }
}

// Global fetch interceptor to handle session expiration and errors
(function() {
    const originalFetch = window.fetch;
    window.fetch = function(...args) {
        return originalFetch.apply(this, args).then(response => {
            const clonedResponse = response.clone();
            const contentType = response.headers.get('content-type');
            if (contentType && contentType.includes('application/json')) {
                clonedResponse.json().then(data => {
                    if (data.code === 'SESSION_EXPIRED' || data.error === 'Session expired. Please log in again.') {
                        console.warn('Session expired, redirecting to login...');
                        if (typeof showNotification !== 'undefined') {
                            showNotification('Your session has expired. Please log in again.', 'warning');
                        }
                        setTimeout(() => {
                            window.location.href = '/auth/login?next=' + encodeURIComponent(window.location.pathname);
                        }, 1500);
                    }
                }).catch(() => {});
            }
            if (response.status === 401) {
                clonedResponse.text().then(text => {
                    if (text.includes('<!DOCTYPE') || text.includes('<!doctype')) {
                        window.location.href = '/auth/login?next=' + encodeURIComponent(window.location.pathname);
                    }
                }).catch(() => {});
            }
            return response;
        }).catch(error => {
            console.error('Fetch error:', error);
            throw error;
        });
    };
})();

document.addEventListener('DOMContentLoaded', function() {
    // Auto-dismiss alerts after 5 seconds
    const alerts = document.querySelectorAll('.alert');
    alerts.forEach(function(alert) {
        setTimeout(function() {
            const bsAlert = new bootstrap.Alert(alert);
            bsAlert.close();
        }, 5000);
    });

    // Initialize tooltips
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function(tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });

    // Sidebar navigation dropdown toggle
    const navDropdowns = document.querySelectorAll('.sidebar .nav-dropdown > .nav-link');
    navDropdowns.forEach(function(dropdownToggle) {
        dropdownToggle.addEventListener('click', function(e) {
            e.preventDefault();
            const parent = this.parentElement;

            // Close other open dropdowns
            if (!parent.classList.contains('open')) {
                document.querySelectorAll('.sidebar .nav-dropdown.open').forEach(openDropdown => {
                    if (openDropdown !== parent) {
                        openDropdown.classList.remove('open');
                    }
                });
            }

            // Toggle current dropdown
            parent.classList.toggle('open');
        });
    });

    // Mobile sidebar toggle functionality - with retry logic
    function attachSidebarListeners() {
        const sidebarToggle = document.getElementById('sidebarToggle');
        const sidebar = document.getElementById('sidebar');
        const sidebarOverlay = document.getElementById('sidebarOverlay');
        
        if (!sidebarToggle || !sidebar) {
            console.warn('Sidebar elements not ready, will retry');
            setTimeout(attachSidebarListeners, 100);
            return;
        }
        
        function handleSidebarToggle(e) {
            e.preventDefault();
            e.stopPropagation();
            sidebar.classList.toggle('open');
            if (sidebarOverlay) {
                sidebarOverlay.classList.toggle('active');
            }
            // Prevent body scroll when sidebar is open
            if (sidebar.classList.contains('open')) {
                document.body.style.overflow = 'hidden';
            } else {
                document.body.style.overflow = '';
            }
        }
        
        // Remove existing listeners to prevent duplicates
        sidebarToggle.removeEventListener('click', handleSidebarToggle);
        sidebarToggle.removeEventListener('touchstart', handleSidebarToggle);
        
        // Attach listeners with bubbling phase
        sidebarToggle.addEventListener('click', handleSidebarToggle, false);
        sidebarToggle.addEventListener('touchstart', handleSidebarToggle, false);
    }
    
    attachSidebarListeners();

    // Sidebar collapse button (desktop collapse) and close button (mobile close)
    function attachCollapseListeners() {
        const sidebarCollapse = document.getElementById('sidebarCollapse');
        const sidebarClose = document.getElementById('sidebarClose');
        const sidebar = document.getElementById('sidebar');
        
        if (!sidebar) {
            setTimeout(attachCollapseListeners, 100);
            return;
        }
        
        if (sidebarCollapse) {
            // Restore collapsed state on page load
            if (localStorage.getItem('sidebarCollapsed') === 'true') {
                sidebar.classList.add('collapsed');
            }
            
            function handleSidebarCollapse(e) {
                if (e) {
                    e.preventDefault();
                    e.stopPropagation();
                }
                sidebar.classList.toggle('collapsed');
                // Save the state
                localStorage.setItem('sidebarCollapsed', sidebar.classList.contains('collapsed'));
            }
            
            sidebarCollapse.removeEventListener('click', handleSidebarCollapse);
            sidebarCollapse.removeEventListener('touchstart', handleSidebarCollapse);
            sidebarCollapse.addEventListener('click', handleSidebarCollapse, false);
            sidebarCollapse.addEventListener('touchstart', handleSidebarCollapse, false);
        }
        
        // Close button for mobile sidebar
        if (sidebarClose) {
            function handleSidebarClose(e) {
                if (e) {
                    e.preventDefault();
                    e.stopPropagation();
                }
                sidebar.classList.remove('open');
                const overlay = document.getElementById('sidebarOverlay');
                if (overlay) {
                    overlay.classList.remove('active');
                }
                document.body.style.overflow = '';
            }
            
            sidebarClose.removeEventListener('click', handleSidebarClose);
            sidebarClose.removeEventListener('touchstart', handleSidebarClose);
            sidebarClose.addEventListener('click', handleSidebarClose, false);
            sidebarClose.addEventListener('touchstart', handleSidebarClose, false);
        }
    }
    
    attachCollapseListeners();
    
    // Close sidebar when overlay is clicked
    function attachOverlayListener() {
        const sidebarOverlay = document.getElementById('sidebarOverlay');
        const sidebar = document.getElementById('sidebar');
        
        if (!sidebarOverlay || !sidebar) {
            setTimeout(attachOverlayListener, 100);
            return;
        }
        
        function handleOverlayClick(e) {
            e.preventDefault();
            e.stopPropagation();
            sidebar.classList.remove('open');
            sidebarOverlay.classList.remove('active');
            document.body.style.overflow = '';
        }
        
        sidebarOverlay.removeEventListener('click', handleOverlayClick);
        sidebarOverlay.addEventListener('click', handleOverlayClick, false);
    }
    
    attachOverlayListener();
    
    // Close sidebar when a nav link is clicked (mobile only - keep collapsed state on desktop)
    function attachNavLinkListeners() {
        const sidebar = document.getElementById('sidebar');
        const sidebarOverlay = document.getElementById('sidebarOverlay');
        
        if (!sidebar) {
            setTimeout(attachNavLinkListeners, 100);
            return;
        }
        
        const navLinks = sidebar.querySelectorAll('.nav-link, .nav-dropdown-link');
        navLinks.forEach(function(link) {
            link.addEventListener('click', function(e) {
                // Skip if this is a dropdown toggle
                if (link.classList.contains('nav-link') && link.parentElement.classList.contains('nav-dropdown')) {
                    return;
                }
                
                setTimeout(function() {
                    // Mobile: close the 'open' sidebar (off-screen state)
                    if (window.innerWidth <= 991 && sidebar.classList.contains('open')) {
                        sidebar.classList.remove('open');
                        if (sidebarOverlay) {
                            sidebarOverlay.classList.remove('active');
                        }
                        document.body.style.overflow = '';
                    }
                }, 50);
            }, false);
        });
    }
    
    attachNavLinkListeners();
    
    // Mobile user profile dropdown - ensure Bootstrap initialization
    const mobileUserDropdown = document.getElementById('mobileUserDropdown');
    if (mobileUserDropdown) {
        try {
            // Destroy any existing instance first
            let instance = bootstrap.Dropdown.getInstance(mobileUserDropdown);
            if (instance) instance.dispose();
            // Create new instance
            new bootstrap.Dropdown(mobileUserDropdown);
        } catch(e) {
            console.warn('Bootstrap Dropdown initialization:', e);
        }
    }
});

// Helper function to show notifications
function showNotification(message, type) {
    const alertDiv = document.createElement('div');
    alertDiv.className = `alert alert-${type} alert-dismissible fade show position-fixed`;
    alertDiv.style.cssText = 'top: 20px; right: 20px; z-index: 9999; min-width: 300px;';
    alertDiv.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    document.body.appendChild(alertDiv);

    setTimeout(function() {
        if (alertDiv.parentNode) {
            alertDiv.remove();
        }
    }, 5000);
}

// Helper function to check if we should handle keyboard shortcuts
function shouldHandleShortcuts() {
    const tag = document.activeElement ? document.activeElement.tagName : null;
    const editable = document.activeElement ? document.activeElement.isContentEditable : false;
    
    // Don't handle if in an input, textarea, or content editable
    if (tag === 'INPUT' || tag === 'TEXTAREA' || editable) {
        return false;
    }
    
    // Don't handle if a modal is open
    const openModals = document.querySelectorAll('.modal.show');
    if (openModals.length > 0) {
        return false;
    }
    
    return true;
}

// Quick Navigation handlers: click, touch feedback, and keyboard shortcuts
document.addEventListener('DOMContentLoaded', function() {
    const quickButtons = document.querySelectorAll('.quick-nav-button');
    quickButtons.forEach(btn => {
        // Click navigation
        btn.addEventListener('click', function(e) {
            const url = this.dataset.url;
            if (url) {
                window.location.href = url;
            }
        });

        // Touch / fast feedback
        btn.addEventListener('touchstart', function() {
            this.classList.add('active');
        }, {passive: true});
        btn.addEventListener('touchend', function() {
            this.classList.remove('active');
        });
    });

    // Keyboard shortcuts (single-letter): only when not typing in inputs
    document.addEventListener('keydown', function(e) {
        // Check if we should handle shortcuts
        if (!shouldHandleShortcuts()) return;
        
        const key = e.key.toUpperCase();
        if (!key || key.length !== 1) return;
        
        // Open shortcut modal with ? or Shift+/
        if (key === '?' || (e.shiftKey && e.key === '/')) {
            const modalEl = document.getElementById('shortcutModal');
            if (modalEl) {
                const bsModal = new bootstrap.Modal(modalEl);
                bsModal.show();
                e.preventDefault();
                return;
            }
        }
        
        // Define keyboard shortcuts mapping with correct Flask routes
        // Full paths based on blueprint prefix + route: 
        // sales_bp (/sales) + /sales = /sales/sales
        // sales_bp (/sales) + /sales/history = /sales/sales/history
        // sales_bp (/sales) + /returns = /sales/returns
        // customers_bp (/customers) + /customers = /customers/customers
        // inventory_bp (/inventory) + /inventory = /inventory/inventory
        // expenses_bp (/expenses) + /expenses = /expenses/expenses
        // reports_bp (/reports) + /reports = /reports/reports
        const shortcuts = {
            'N': '/sales/sales',               // New Sale
            'C': '/customers/customers',        // Customers
            'P': '/inventory/inventory',        // Products  
            'H': '/sales/sales/history',        // Sales History (FIXED - was /sales/history)
            'R': '/sales/returns',              // Returns
            'B': '/sales/sales?held=true',      // Hold Bills
            'E': '/expenses/expenses',          // Expenses
            'T': '/reports/reports'             // Reports
        };
        
        // Check if the pressed key matches a shortcut
        if (shortcuts[key]) {
            e.preventDefault();
            console.log('Keyboard shortcut pressed:', key, '->', shortcuts[key]);
            window.location.href = shortcuts[key];
            return;
        }
        
        // Fallback: Match data-shortcut on quick-nav-button elements
        const target = Array.from(quickButtons).find(b => (b.dataset.shortcut || '').toUpperCase() === key);
        if (target) {
            e.preventDefault();
            target.classList.add('active');
            setTimeout(() => target.classList.remove('active'), 150);
            const url = target.dataset.url;
            if (url) window.location.href = url;
        }
    });

    // Shortcut help button
    const shortcutHelpBtn = document.getElementById('shortcutHelpBtn');
    if (shortcutHelpBtn) {
        shortcutHelpBtn.addEventListener('click', function() {
            const modalEl = document.getElementById('shortcutModal');
            if (modalEl) {
                const bsModal = new bootstrap.Modal(modalEl);
                bsModal.show();
            }
        });
    }
});

// On-screen keyboard: create overlay and wire to focused input
document.addEventListener('DOMContentLoaded', function() {
    const kbBtn = document.getElementById('onScreenKeyboardBtn');
    if (!kbBtn) return;

    // build keyboard markup - side panel
    function buildKeyboard() {
        const overlay = document.createElement('div');
        overlay.className = 'onscreen-kb-overlay';
        overlay.id = 'onscreenKbOverlay';

        const kb = document.createElement('div');
        kb.className = 'onscreen-kb';

        // Numbers row (1-0)
        const numRow = document.createElement('div'); 
        numRow.className = 'kb-row';
        '1 2 3 4 5 6 7 8 9 0'.split(' ').forEach(n => {
            const key = document.createElement('div'); 
            key.className='kb-key'; 
            key.textContent = n; 
            key.addEventListener('click', ()=>sendKey(n)); 
            numRow.appendChild(key);
        });
        kb.appendChild(numRow);

        // QWERTY rows
        const rows = [
            'Q W E R'.split(' '),
            'T Y U I'.split(' '),
            'O P A S'.split(' '),
            'D F G H'.split(' '),
            'J K L Z'.split(' '),
            'X C V B'.split(' '),
            'N M'.split(' '),
        ];

        rows.forEach((rowKeys) => {
            const row = document.createElement('div');
            row.className = 'kb-row';
            rowKeys.forEach(k => {
                const key = document.createElement('div');
                key.className = 'kb-key';
                key.textContent = k.toLowerCase();
                key.addEventListener('click', () => sendKey(k.toLowerCase()));
                row.appendChild(key);
            });
            kb.appendChild(row);
        });

        // Special keys
        const specialRow1 = document.createElement('div');
        specialRow1.className = 'kb-row';
        ['.', ',', '-', '+'].forEach(k => {
            const key = document.createElement('div');
            key.className = 'kb-key';
            key.textContent = k;
            key.addEventListener('click', () => sendKey(k));
            specialRow1.appendChild(key);
        });
        kb.appendChild(specialRow1);

        const specialRow2 = document.createElement('div');
        specialRow2.className = 'kb-row';
        ['@', '$', '%', '/'].forEach(k => {
            const key = document.createElement('div');
            key.className = 'kb-key';
            key.textContent = k;
            key.addEventListener('click', () => sendKey(k));
            specialRow2.appendChild(key);
        });
        kb.appendChild(specialRow2);

        // actions
        const actionRow = document.createElement('div'); 
        actionRow.className = 'kb-actions';
        
        const btnSpace = document.createElement('div'); 
        btnSpace.className='kb-key kb-wide'; 
        btnSpace.textContent='Space'; 
        btnSpace.addEventListener('click', ()=>sendKey(' '));

        const btnBack = document.createElement('div'); 
        btnBack.className='kb-key kb-wide'; 
        btnBack.textContent='← Backspace'; 
        btnBack.addEventListener('click', ()=>sendKey('BACKSPACE'));

        const btnEnter = document.createElement('div'); 
        btnEnter.className='kb-key kb-wide'; 
        btnEnter.style.background = 'rgba(16,185,129,0.3)';
        btnEnter.style.borderColor = 'rgba(16,185,129,0.6)';
        btnEnter.textContent='⏎ Enter'; 
        btnEnter.addEventListener('click', ()=>sendKey('ENTER'));

        const btnClose = document.createElement('button'); 
        btnClose.className='btn btn-light'; 
        btnClose.style.width='100%';
        btnClose.textContent='Close Keyboard';

        btnClose.addEventListener('click', ()=>{ 
            overlay.classList.remove('show'); 
            const mainContent = document.querySelector('.main-content'); 
            if(mainContent) mainContent.classList.remove('kb-open'); 
        });

        actionRow.appendChild(btnSpace);
        actionRow.appendChild(btnBack);
        actionRow.appendChild(btnEnter);
        actionRow.appendChild(btnClose);
        kb.appendChild(actionRow);

        overlay.appendChild(kb);
        document.body.appendChild(overlay);
    }

    function sendKey(key) {
        const active = document.activeElement;
        let target = (active && (active.tagName === 'INPUT' || active.tagName === 'TEXTAREA')) ? active : window._lastFocusedInput;
        
        if (!target || (target.tagName !== 'INPUT' && target.tagName !== 'TEXTAREA')) {
            return;
        }
        
        target.focus();
        
        let currentVal = target.value || '';
        let newVal = currentVal;
        
        if (key === 'BACKSPACE') {
            newVal = currentVal.slice(0, -1);
        } else if (key === 'ENTER') {
            target.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', bubbles: true }));
            target.dispatchEvent(new Event('change', { bubbles: true }));
            return;
        } else {
            // For number inputs, validate before adding
            const testVal = currentVal + key;
            if (target.type === 'number') {
                if (!/^-?\d*\.?\d*$/.test(testVal) && testVal !== '') {
                    return;
                }
            }
            newVal = testVal;
        }
        
        target.value = newVal;
        
        // Set cursor to end 
        setTimeout(() => {
            target.setSelectionRange(newVal.length, newVal.length);
        }, 0);
        
        target.dispatchEvent(new Event('input', { bubbles: true }));
        target.dispatchEvent(new Event('change', { bubbles: true }));
    }

    // store last focused input for when keyboard opened
    document.addEventListener('focusin', function(e) {
        const t = e.target;
        if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) {
            window._lastFocusedInput = t;
            
            // Auto-close keyboard when focusing on search fields to avoid covering them
            const searchKeywords = ['search', 'filter', 'query'];
            const isSearchField = searchKeywords.some(kw => 
                (t.id && t.id.toLowerCase().includes(kw)) ||
                (t.placeholder && t.placeholder.toLowerCase().includes(kw)) ||
                (t.name && t.name.toLowerCase().includes(kw))
            );
            
            if (isSearchField) {
                const overlay = document.getElementById('onscreenKbOverlay');
                if (overlay && overlay.classList.contains('show')) {
                    overlay.classList.remove('show');
                    const mainContent = document.querySelector('.main-content');
                    if (mainContent) mainContent.classList.remove('kb-open');
                }
            }
        }
    });

    // lazy-build keyboard
    kbBtn.addEventListener('click', function() {
        let overlay = document.getElementById('onscreenKbOverlay');
        if (!overlay) buildKeyboard();
        overlay = document.getElementById('onscreenKbOverlay');
        const mainContent = document.querySelector('.main-content');
        const isShowing = overlay.classList.toggle('show');
        if (mainContent) {
            if (isShowing) mainContent.classList.add('kb-open');
            else mainContent.classList.remove('kb-open');
        }
        // focus last input to ensure typing target
        if (window._lastFocusedInput) window._lastFocusedInput.focus();
    });
});

// Fullscreen toggle
document.addEventListener('DOMContentLoaded', function() {
    const fullscreenBtn = document.getElementById('fullscreenBtn');
    const fullscreenIcon = document.getElementById('fullscreenIcon');

    if (!fullscreenBtn || !fullscreenIcon) return;

    function isFullscreen() {
        return !!(document.fullscreenElement || document.webkitFullscreenElement || document.msFullscreenElement);
    }

    function enterFullscreen() {
        const el = document.documentElement;
        if (el.requestFullscreen) el.requestFullscreen();
        else if (el.webkitRequestFullscreen) el.webkitRequestFullscreen();
        else if (el.msRequestFullscreen) el.msRequestFullscreen();
    }

    function exitFullscreen() {
        if (document.exitFullscreen) document.exitFullscreen();
        else if (document.webkitExitFullscreen) document.webkitExitFullscreen();
        else if (document.msExitFullscreen) document.msExitFullscreen();
    }

    function updateIcon() {
        if (isFullscreen()) {
            fullscreenIcon.classList.remove('fa-expand');
            fullscreenIcon.classList.add('fa-compress');
        } else {
            fullscreenIcon.classList.remove('fa-compress');
            fullscreenIcon.classList.add('fa-expand');
        }
    }

    fullscreenBtn.addEventListener('click', function() {
        if (isFullscreen()) exitFullscreen();
        else enterFullscreen();
    });

    ['fullscreenchange', 'webkitfullscreenchange', 'msfullscreenchange'].forEach(evt => {
        document.addEventListener(evt, updateIcon);
    });

    // Keyboard shortcut: Ctrl+Shift+F to toggle fullscreen
    document.addEventListener('keydown', function(e) {
        if (e.ctrlKey && e.shiftKey && (e.key === 'F' || e.key === 'f')) {
            e.preventDefault();
            if (isFullscreen()) exitFullscreen();
            else enterFullscreen();
        }
    });

    // When user returns to the tab, prompt to re-enter fullscreen (user gesture required)
    function showReenterPrompt() {
        if (document.getElementById('reenterFullscreenPrompt')) return;
        const wrapper = document.createElement('div');
        wrapper.id = 'reenterFullscreenPrompt';
        wrapper.style.cssText = 'position:fixed;bottom:16px;left:16px;z-index:11000;';

        const btn = document.createElement('button');
        btn.className = 'btn btn-primary';
        btn.textContent = 'Return to fullscreen';
        btn.addEventListener('click', function() {
            enterFullscreen();
            wrapper.remove();
        }, { once: true });

        const close = document.createElement('button');
        close.className = 'btn btn-light ms-2';
        close.textContent = 'Dismiss';
        close.addEventListener('click', function() { wrapper.remove(); }, { once: true });

        wrapper.appendChild(btn);
        wrapper.appendChild(close);
        document.body.appendChild(wrapper);
    }

    document.addEventListener('visibilitychange', function() {
        if (document.visibilityState === 'visible' && !isFullscreen()) {
            // show prompt to re-enter fullscreen; user must click
            showReenterPrompt();
        }
    });
});

// Calculator Functionality
(function() {
    let expression = '';
    let isResult = false;

    window.calcAppend = function(val) {
        const display = document.getElementById('calcDisplay');
        if (!display) return;

        if (val === 'C') {
            expression = '';
            display.value = '0';
            isResult = false;
        } else if (val === 'DEL') {
            expression = expression.toString().slice(0, -1);
            display.value = expression || '0';
            isResult = false;
        } else {
            const operators = ['+', '-', '*', '/', '.', '%'];
            if (isResult && !operators.includes(val)) {
                expression = '';
            }
            isResult = false;

            // Prevent multiple operators in sequence
            const lastChar = expression.toString().slice(-1);

            if (operators.includes(val)) {
                if (operators.includes(lastChar)) {
                    expression = expression.slice(0, -1) + val;
                } else if (expression === '' && val !== '.') {
                    return; // Don't start with an operator (except decimal)
                } else {
                    expression += val;
                }
            } else {
                expression += val;
            }
            display.value = expression || '0';
        }
    };

    window.calcResult = function() {
        const display = document.getElementById('calcDisplay');
        if (!display) return;

        try {
            if (!expression) return;
            // Safe evaluation
            const result = Function('"use strict";return (' + expression + ')')();
            // Format to avoid long decimals
            const formatted = Math.round(result * 100000000) / 100000000;
            display.value = formatted;
            expression = formatted.toString();
            isResult = true;
        } catch (e) {
            display.value = 'Error';
            expression = '';
            isResult = false;
        }
    };

    function handleCalcKeyboard(e) {
        // Only act if the calculator is visible
        const calcEl = document.getElementById('draggableCalculator');
        if (!calcEl || calcEl.style.display === 'none') {
            return;
        }

        // Allow tabbing out, but prevent other default actions
        if (e.key === 'Tab') {
            return;
        }
        
        // Don't prevent default if user is typing in another input
        if (document.activeElement && (document.activeElement.tagName === 'INPUT' || document.activeElement.tagName === 'TEXTAREA')) {
             // unless it's the calc display itself (which is readonly anyway)
             if (document.activeElement.id !== 'calcDisplay') return;
        }
        
        e.preventDefault();

        const key = e.key;

        if (key >= '0' && key <= '9') {
            calcAppend(key);
        } else if (['+', '-', '*', '/', '.', '%'].includes(key)) {
            calcAppend(key);
        } else if (key === 'Enter' || key === '=') {
            calcResult();
        } else if (key === 'Backspace') {
            calcAppend('DEL');
        } else if (key.toLowerCase() === 'c') {
            calcAppend('C');
        } else if (key === 'Escape') {
            calcEl.style.display = 'none';
        }
    }

    // Drag Functionality
    function dragElement(elmnt) {
        var pos1 = 0, pos2 = 0, pos3 = 0, pos4 = 0;
        const header = document.getElementById("calcHeader");
        if (header) {
            header.onmousedown = dragMouseDown;
        }

        function dragMouseDown(e) {
            e = e || window.event;
            e.preventDefault();
            pos3 = e.clientX;
            pos4 = e.clientY;
            document.onmouseup = closeDragElement;
            document.onmousemove = elementDrag;
        }

        function elementDrag(e) {
            e = e || window.event;
            e.preventDefault();
            pos1 = pos3 - e.clientX;
            pos2 = pos4 - e.clientY;
            pos3 = e.clientX;
            pos4 = e.clientY;
            elmnt.style.top = (elmnt.offsetTop - pos2) + "px";
            elmnt.style.left = (elmnt.offsetLeft - pos1) + "px";
            elmnt.style.right = 'auto'; // Clear right positioning once moved
        }

        function closeDragElement() {
            document.onmouseup = null;
            document.onmousemove = null;
        }
    }

    // Bind button event and keyboard listener
    document.addEventListener('DOMContentLoaded', function() {
        const calcBtn = document.getElementById('calculatorBtn');
        const calcEl = document.getElementById('draggableCalculator');
        const closeBtn = document.getElementById('closeCalcBtn');

        if (calcBtn && calcEl) {
            calcBtn.addEventListener('click', function() {
                if (calcEl.style.display === 'none') {
                    calcEl.style.display = 'block';
                } else {
                    calcEl.style.display = 'none';
                }
            });
            
            if (closeBtn) {
                closeBtn.addEventListener('click', function() {
                    calcEl.style.display = 'none';
                });
            }

            // Initialize drag
            dragElement(calcEl);

            // Add a single keyboard listener to the document for the calculator
            document.addEventListener('keydown', handleCalcKeyboard);
        }
    });
})();
