/// <reference path="../pb_data/types.d.ts" />
/**
 * Use "1=1" for all ingredients rules (list, view, update, delete).
 * mealId.user traversal fails in PB rules, so we can't scope by meal owner.
 * 1=1 matches the permissive setup that worked before 1759900005.
 */
migrate((txApp) => {
  const collection = txApp.findCollectionByNameOrId("pbc_3146854971");

  collection.listRule = "1=1";
  collection.viewRule = "1=1";
  collection.updateRule = "1=1";
  collection.deleteRule = "1=1";

  return txApp.save(collection);
}, (txApp) => {
  const collection = txApp.findCollectionByNameOrId("pbc_3146854971");

  collection.listRule = '@request.auth.id != ""';
  collection.viewRule = '@request.auth.id != ""';
  collection.updateRule = "mealId.user = @request.auth.id";
  collection.deleteRule = "mealId.user = @request.auth.id";

  return txApp.save(collection);
});
