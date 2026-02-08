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
    """
    components.html("""
    <script>
    (function() {
        // Remove any previously injected button (avoids duplicates on rerun)
        var existing = window.parent.document.getElementById('nano-sidebar-toggle');
        if (existing) existing.remove();

        // Create the floating button in the PARENT document (outside iframe)
        var btn = window.parent.document.createElement('div');
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

        btn.onclick = function() {
            // Streamlit's sidebar toggle button (collapsed state)
            var openBtn = window.parent.document.querySelector(
                '[data-testid="collapsedControl"]'
            );
            if (openBtn) {
                openBtn.click();
                return;
            }
            // Sidebar close button (expanded state) - the X button in sidebar header
            var closeBtn = window.parent.document.querySelector(
                '[data-testid="stSidebar"] button[kind="header"]'
            );
            if (closeBtn) {
                closeBtn.click();
                return;
            }
            // Fallback: try any button in the sidebar header area
            var headerBtn = window.parent.document.querySelector(
                '[data-testid="stSidebar"] header button'
            );
            if (headerBtn) {
                headerBtn.click();
            }
        };

        window.parent.document.body.appendChild(btn);
    })();
    </script>
    """, height=0)
