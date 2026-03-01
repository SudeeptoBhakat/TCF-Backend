document.addEventListener("DOMContentLoaded", () => {
    const gallery = document.querySelector(".gallery-grid");
    if (!gallery) return;

    let sortable = Sortable.create(gallery, {
        animation: 150,
        ghostClass: "sortable-ghost",
        onEnd: function () {
            console.log("Images reordered");
        }
    });
});
