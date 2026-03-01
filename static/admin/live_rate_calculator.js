document.addEventListener("DOMContentLoaded", function () {

    const priceInput = document.getElementById("id_unit_price");
    const weight = document.getElementById("calc_weight");
    const making = document.getElementById("calc_making");
    const result = document.getElementById("calc_price");

    function calculate() {
        const rate = parseFloat(priceInput?.value || 0);
        const w = parseFloat(weight?.value || 0);
        const m = parseFloat(making?.value || 0);

        if (!rate || !w) {
            result.innerText = "0.00";
            return;
        }

        const metal_price = rate * w;
        const making_charge = metal_price * (m / 100);
        const final_price = metal_price + making_charge;

        result.innerText = final_price.toFixed(2);
    }

    if (priceInput) priceInput.addEventListener("input", calculate);
    if (weight) weight.addEventListener("input", calculate);
    if (making) making.addEventListener("input", calculate);
});
