import { initializePriceListFormEventHandlers } from './priceListForm';

function start() {
    initializePriceListFormEventHandlers();
}

window.addEventListener('load', start, false);
