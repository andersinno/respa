import { getEmptyResourceAccessibility } from './resourceForm';

export function updateResourceAccessibilityTotalForms() {
  $('#id_accessibility_summaries-TOTAL_FORMS').val(getResourceAccessibilityCount());
}

export function updateResourceAccessibilityIndices() {
  let $resourceAccessibilityList = $('#resource-accessibility-list').children();
  if (!$resourceAccessibilityList) {
    return;
  }

  $resourceAccessibilityList.each(function (i, resAccessibility) {
    $(resAccessibility).attr('id', $(resAccessibility).attr('id').replace(/-(\d+)/,'-' + i));

    let $inputs = $(resAccessibility).find('input');
    let $buttons = $(resAccessibility).find('button');
    let $dropDowns = $(resAccessibility).find('select');

    //Update select drop down ids.
    $dropDowns.each(function (ddIndex, dropDown) {
      $(dropDown).attr('id', $(dropDown).attr('id').replace(/-(\d+)-/,'-' + i + '-'));
      $(dropDown).attr('name', $(dropDown).attr('name').replace(/-(\d+)-/,'-' + i + '-'));
    });

    //Update button ids.
    $buttons.each(function (buttonIndex, button) {
      $(button).attr('id', $(button).attr('id').replace(/(\d+)/, i));
    });

    //Update input ids (hidden included).
    $inputs.each(function (inputIndex, input) {
      $(input).attr('id', $(input).attr('id').replace(/-(\d+)-/,'-' + i + '-'));
      $(input).attr('name', $(input).attr('name').replace(/-(\d+)-/,'-' + i + '-'));
    });

  });
}

export function addNewResourceAccessibility() {
  let $resourceAccessibilityList = $('#resource-accessibility-list');
  let emptyResourceAccessibility = getEmptyResourceAccessibility();

  if (emptyResourceAccessibility) {
    let newResourceAccessibility = emptyResourceAccessibility.clone();

    $resourceAccessibilityList.append(newResourceAccessibility);

    attachResourceAccessibilityEventHandlers(newResourceAccessibility);
    updateResourceAccessibilityTotalForms();
    updateResourceAccessibilityIndices();
  }

}
export function removeResourceAccessibility(resourceAccessibilityItem) {
  resourceAccessibilityItem.remove();
  updateResourceAccessibilityTotalForms();
  updateResourceAccessibilityIndices();
}

function getResourceAccessibilityCount() {
  return $('#resource-accessibility-list')[0].children.length;
}

function attachResourceAccessibilityEventHandlers(resourceAccessibilityItem) {
  let resourceAccessibilityNum = resourceAccessibilityItem[0].id.match(/(\d+)/)[0];

  let removeButton = resourceAccessibilityItem.find('#remove-resource-accessibility-' + resourceAccessibilityNum)[0];
  removeButton.addEventListener('click', () => removeResourceAccessibility(resourceAccessibilityItem), false);
}
