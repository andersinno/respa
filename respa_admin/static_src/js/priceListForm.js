export function initializePriceListFormEventHandlers() {
    $('#user-group-item-add-more').off('click').on('click', addUserGroupPriceItem);
    $('#event-type-item-add-more').off('click').on('click', addEventTypePriceItem);

    $('#user-group-prices .remove-item').off('click').on('click', { formId: "id_usergroup_prices" }, removePriceItem);
    $('#event-type-prices .remove-item').off('click').on('click', { formId: "id_event_prices" }, removePriceItem);
}

function addUserGroupPriceItem() {
    var total = $('#id_usergroup_prices-TOTAL_FORMS').val();
    $('#user-group-prices').append($('#empty-user-group-item').html().replace(/__prefix__/g, total));
    $('#id_usergroup_prices-TOTAL_FORMS').val(parseInt(total) + 1);

    initializePriceListFormEventHandlers();
}

function addEventTypePriceItem() {
    var total = $('#id_event_prices-TOTAL_FORMS').val();
    $('#event-type-prices').append($('#empty-event-type-item').html().replace(/__prefix__/g, total));
    $('#id_event_prices-TOTAL_FORMS').val(parseInt(total) + 1);

    initializePriceListFormEventHandlers();
}

function removePriceItem(e) {
    let formId = e.data.formId;
    let priceItemValue = $(this).closest('.row').find('[type="hidden"]').first().val();
    var total = $(`#${formId}-TOTAL_FORMS`).val();
    if (priceItemValue) {
        $(this).next('span.hidden-delete-checkbox').find('input').prop("checked", true);
        $(this).closest('.row').hide();
    }
    else {
        $(this).closest('.row').remove();
        $(`#${formId}-TOTAL_FORMS`).val(parseInt(total) - 1);
    }
}
