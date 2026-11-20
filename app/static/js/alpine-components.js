(function () {
    "use strict";

    document.addEventListener("alpine:init", function () {
        /* -------------------------------------------------------------- */
        /* Editor de Docker Compose (abas YAML / .env)                   */
        /* -------------------------------------------------------------- */

        Alpine.data("composeEditor", function () {
            return {
                tab: "yaml",

                setTab(nextTab) {
                    this.tab = nextTab;
                },

                indent(event) {
                    if (event.key !== "Tab") {
                        return;
                    }
                    event.preventDefault();
                    var element = event.target;
                    var start = element.selectionStart;
                    var end = element.selectionEnd;
                    element.value =
                        element.value.substring(0, start) +
                        "  " +
                        element.value.substring(end);
                    element.selectionStart = start + 2;
                    element.selectionEnd = start + 2;
                },
            };
        });

        /* -------------------------------------------------------------- */
        /* Confirmação de remoção de imagem (modal)                      */
        /* -------------------------------------------------------------- */

        Alpine.data("imageList", function () {
            return {
                confirmOpen: false,
                target: "",

                ask(identifier) {
                    this.target = identifier;
                    this.confirmOpen = true;
                },

                cancel() {
                    this.confirmOpen = false;
                },
            };
        });
    });
})();
