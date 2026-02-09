#!/usr/bin/env python3
"""
Floating sidebar toggle button for Streamlit pages.

Uses st.components.v1.html() which executes JS in a same-origin iframe,
allowing access to window.parent.document to toggle the sidebar.
"""

import streamlit.components.v1 as components


def floating_sidebar_toggle():
    """
    Render a floating button at the bottom-left that toggles the sidebar.

    Uses st.components.v1.html() instead of st.markdown() because
    st.markdown sanitizes onclick handlers, while components.html()
    runs JS in a same-origin iframe with parent document access.

    Strategy: try multiple selector approaches to find and click
    Streamlit's internal expand/collapse buttons, then fall back
    to direct CSS manipulation if no buttons are found.
    """
    components.html("""
    <script>
    (function() {
        var parentDoc = window.parent.document;

        // Remove any previously injected button (avoids duplicates on rerun)
        var existing = parentDoc.getElementById('nano-sidebar-toggle');
        if (existing) existing.remove();

        // Create the floating button in the PARENT document (outside iframe)
        var btn = parentDoc.createElement('div');
        btn.id = 'nano-sidebar-toggle';
        btn.innerHTML = '&#9776;';  // hamburger icon
        btn.title = 'Toggle sidebar';
        btn.style.cssText = [
            'position: fixed',
            'bottom: 24px',
            'left: 24px',
            'z-index: 999999',
            'width: 48px',
            'height: 48px',
            'border-radius: 50%',
            'background: #ff4b4b',
            'color: white',
            'font-size: 22px',
            'display: flex',
            'align-items: center',
            'justify-content: center',
            'cursor: pointer',
            'box-shadow: 0 3px 12px rgba(0,0,0,0.3)',
            'transition: transform 0.2s, background 0.2s',
            'user-select: none'
        ].join(';');

        btn.onmouseenter = function() {
            btn.style.transform = 'scale(1.12)';
            btn.style.background = '#ff6b6b';
        };
        btn.onmouseleave = function() {
            btn.style.transform = 'scale(1)';
            btn.style.background = '#ff4b4b';
        };

        // Helper: try a list of CSS selectors, click the first match found
        function clickFirst(selectors) {
            for (var i = 0; i < selectors.length; i++) {
                try {
                    var el = parentDoc.querySelector(selectors[i]);
                    if (el) {
                        el.click();
                        return true;
                    }
                } catch(e) {}
            }
            return false;
        }

        // Helper: check if sidebar is currently open
        function isSidebarOpen() {
            var sidebar = parentDoc.querySelector('[data-testid="stSidebar"]');
            if (!sidebar) return false;
            // Check multiple signals: offsetWidth, aria-expanded, display
            if (sidebar.getAttribute('aria-expanded') === 'false') return false;
            if (sidebar.getAttribute('aria-expanded') === 'true') return true;
            return sidebar.offsetWidth > 50;
        }

        btn.onclick = function(evt) {
            evt.stopPropagation();
            evt.preventDefault();

            var sidebarOpen = isSidebarOpen();

            if (sidebarOpen) {
                // ============= CLOSE the sidebar =============
                var closed = clickFirst([
                    // data-testid based selectors (Streamlit 1.28+)
                    '[data-testid="stSidebar"] [data-testid="baseButton-header"]',
                    '[data-testid="stSidebar"] [data-testid="baseButton-headerNoPadding"]',
                    // aria-label based
                    '[data-testid="stSidebar"] button[aria-label*="Close"]',
                    '[data-testid="stSidebar"] button[aria-label*="close"]',
                    '[data-testid="stSidebar"] button[aria-label*="Collapse"]',
                    '[data-testid="stSidebar"] button[aria-label*="collapse"]',
                    // Streamlit kind attribute (React prop rendered to DOM)
                    '[data-testid="stSidebar"] button[kind="header"]',
                    '[data-testid="stSidebar"] button[kind="headerNoPadding"]',
                ]);

                if (closed) return;

                // Heuristic: first small button with SVG inside sidebar
                var sidebar = parentDoc.querySelector('[data-testid="stSidebar"]');
                if (sidebar) {
                    var btns = sidebar.querySelectorAll('button');
                    for (var k = 0; k < btns.length; k++) {
                        if (btns[k].querySelector('svg') && btns[k].offsetWidth < 60) {
                            btns[k].click();
                            return;
                        }
                    }
                }

                // CSS fallback: hide sidebar directly
                if (sidebar) {
                    sidebar.setAttribute('aria-expanded', 'false');
                    sidebar.style.width = '0px';
                    sidebar.style.minWidth = '0px';
                    sidebar.style.overflow = 'hidden';
                    // Show the collapsed control so the expand button appears
                    var ctrl = parentDoc.querySelector('[data-testid="collapsedControl"]')
                            || parentDoc.querySelector('[data-testid="stSidebarCollapsedControl"]');
                    if (ctrl) ctrl.style.display = '';
                }

            } else {
                // ============= OPEN the sidebar =============
                // Try the collapsed control container (click button inside, or container)
                var expandContainerSelectors = [
                    '[data-testid="collapsedControl"]',
                    '[data-testid="stSidebarCollapsedControl"]',
                ];
                for (var i = 0; i < expandContainerSelectors.length; i++) {
                    try {
                        var container = parentDoc.querySelector(expandContainerSelectors[i]);
                        if (container) {
                            var innerBtn = container.querySelector('button');
                            if (innerBtn) {
                                innerBtn.click();
                                return;
                            }
                            container.click();
                            return;
                        }
                    } catch(e) {}
                }

                // Try standalone expand button selectors
                var opened = clickFirst([
                    'button[aria-label*="Open sidebar"]',
                    'button[aria-label*="open sidebar"]',
                    'button[aria-label*="Expand"]',
                    'button[aria-label*="expand"]',
                ]);

                if (opened) return;

                // Heuristic: find small button NOT inside sidebar, near top-left
                var sidebar = parentDoc.querySelector('[data-testid="stSidebar"]');
                var allBtns = parentDoc.querySelectorAll('button');
                for (var m = 0; m < allBtns.length; m++) {
                    var b = allBtns[m];
                    var rect = b.getBoundingClientRect();
                    var inSidebar = sidebar && sidebar.contains(b);
                    if (!inSidebar && rect.top < 80 && rect.left < 80
                        && rect.width < 60 && rect.width > 0) {
                        b.click();
                        return;
                    }
                }

                // CSS fallback: show sidebar directly
                if (sidebar) {
                    sidebar.setAttribute('aria-expanded', 'true');
                    sidebar.style.width = '';
                    sidebar.style.minWidth = '';
                    sidebar.style.overflow = '';
                    // Hide the collapsed control
                    var ctrl = parentDoc.querySelector('[data-testid="collapsedControl"]')
                            || parentDoc.querySelector('[data-testid="stSidebarCollapsedControl"]');
                    if (ctrl) ctrl.style.display = 'none';
                }
            }
        };

        parentDoc.body.appendChild(btn);
    })();
    </script>
    """, height=0)
