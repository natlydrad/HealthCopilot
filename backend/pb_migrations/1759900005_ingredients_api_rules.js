/// <reference path="../pb_data/types.d.ts" />
/**
 * Fix: ingredients had listRule/deleteRule = null (locked = superuser only).
 * Regular users got 403 on delete, so Clear appeared to work but didn't persist.
 * Allow meal owner to list/view/update/delete their meal's ingredients.
 */
migrate((txApp) => {
  const collection = txApp.findCollectionByNameOrId("pbc_3146854971");

  // Allow authenticated user who owns the meal to access its ingredients
  // mealId.user = the meal's owner; must match logged-in user
  const rule = '@request.auth.id != "" && mealId.user = @request.auth.id';

  collection.listRule = rule;
  collection.viewRule = rule;
  collection.updateRule = rule;
  collection.deleteRule = rule;

  return txApp.save(collection);
}, (txApp) => {
  const collection = txApp.findCollectionByNameOrId("pbc_3146854971");

  collection.listRule = null;
  collection.viewRule = null;
  collection.updateRule = null;
  collection.deleteRule = null;

  return txApp.save(collection);
});
