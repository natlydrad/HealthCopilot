/// <reference path="../pb_data/types.d.ts" />
/**
 * Fix: 1759900005 used mealId.user in listRule - hid all ingredients (legacy data
 * or relation traversal may not match). Relax list/view to any authenticated user
 * so ingredients show again. Keep deleteRule strict so Clear still works.
 */
migrate((txApp) => {
  const collection = txApp.findCollectionByNameOrId("pbc_3146854971");

  // List/view: any authenticated user (restore visibility)
  collection.listRule = '@request.auth.id != ""';
  collection.viewRule = '@request.auth.id != ""';

  // Update/delete: only meal owner (keeps Clear working)
  collection.updateRule = 'mealId.user = @request.auth.id';
  collection.deleteRule = 'mealId.user = @request.auth.id';

  return txApp.save(collection);
}, (txApp) => {
  const collection = txApp.findCollectionByNameOrId("pbc_3146854971");

  // Revert to previous rule (restore 1759900005 behavior)
  const rule = '@request.auth.id != "" && mealId.user = @request.auth.id';
  collection.listRule = rule;
  collection.viewRule = rule;
  collection.updateRule = rule;
  collection.deleteRule = rule;

  return txApp.save(collection);
});
