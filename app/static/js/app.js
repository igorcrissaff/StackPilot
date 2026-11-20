(function () {
    "use strict";

    /* ------------------------------------------------------------------ */
    /* Painéis HTMX (compose / logs)                                       */
    /* ------------------------------------------------------------------ */

    function closePanel(panelId) {
        var panel = document.getElementById(panelId);
        if (panel) {
            panel.outerHTML = '<div id="' + panelId + '" class="mt-4"></div>';
        }
    }

    /* ------------------------------------------------------------------ */
    /* Drawer de navegação (mobile)                                        */
    /* ------------------------------------------------------------------ */

    function toggleDrawer(drawerId) {
        var drawer = document.getElementById(drawerId);
        if (drawer) {
            drawer.classList.toggle("hidden");
        }
    }

    function closeDrawer(drawerId) {
        var drawer = document.getElementById(drawerId);
        if (drawer) {
            drawer.classList.add("hidden");
        }
    }

    /* ------------------------------------------------------------------ */
    /* Abas da página Docker                                               */
    /* ------------------------------------------------------------------ */

    function showDockerTab(tab) {
        var isImages = tab === "images";
        var imagesPane = document.getElementById("pane-images");
        var containersPane = document.getElementById("pane-containers");
        var imagesTab = document.getElementById("tab-images");
        var containersTab = document.getElementById("tab-containers");

        if (imagesPane) {
            imagesPane.classList.toggle("hidden", !isImages);
        }
        if (containersPane) {
            containersPane.classList.toggle("hidden", isImages);
        }

        var activeClass =
            "px-4 py-2.5 text-xs font-semibold text-sky-400 border-b-2 border-sky-500 transition";
        var inactiveClass =
            "px-4 py-2.5 text-xs font-semibold text-slate-400 border-b-2 border-transparent hover:text-white transition";

        if (imagesTab) {
            imagesTab.className = isImages ? activeClass : inactiveClass;
        }
        if (containersTab) {
            containersTab.className = isImages ? inactiveClass : activeClass;
        }
    }

    /* ------------------------------------------------------------------ */
    /* Filtro de tabelas                                                   */
    /* ------------------------------------------------------------------ */

    function filterRows(input) {
        var selector = input.getAttribute("data-filter-rows");
        if (!selector) {
            return;
        }
        var term = input.value.toLowerCase();
        document.querySelectorAll(selector).forEach(function (row) {
            var match = row.innerText.toLowerCase().indexOf(term) !== -1;
            row.style.display = match ? "" : "none";
        });
    }

    /* ------------------------------------------------------------------ */
    /* Delegação de eventos                                                */
    /* ------------------------------------------------------------------ */

    document.addEventListener("click", function (event) {
        var target = event.target.closest("[data-action]");
        if (target) {
            var action = target.getAttribute("data-action");

            switch (action) {
                case "close-panel":
                    event.preventDefault();
                    closePanel(target.getAttribute("data-panel"));
                    break;
                case "copy":
                    event.preventDefault();
                    var source = document.querySelector(target.getAttribute("data-copy-target"));
                    if (source && navigator.clipboard) {
                        navigator.clipboard.writeText(source.innerText || source.textContent || "");
                    }
                    break;
                case "toggle-drawer":
                    event.preventDefault();
                    toggleDrawer(target.getAttribute("data-drawer"));
                    break;
                case "close-drawer":
                    event.preventDefault();
                    closeDrawer(target.getAttribute("data-drawer"));
                    break;
                case "docker-tab":
                    event.preventDefault();
                    showDockerTab(target.getAttribute("data-tab"));
                    break;
            }
            return;
        }

        var overlay = event.target.closest("[data-drawer-overlay]");
        if (overlay && event.target === overlay) {
            overlay.classList.add("hidden");
        }
    });

    document.addEventListener("input", function (event) {
        var input = event.target.closest("[data-filter-rows]");
        if (input) {
            filterRows(input);
        }
    });
})();
