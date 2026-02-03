/// <reference path="../pb_data/types.d.ts" />
/**
 * Restore ingredients visibility: use "1=1" for list/view (same as parsing_cache,
 * brand_foods). @request.auth.id != "" was still returning empty—this matches
 * the permissive rule that worked before 1759900005.
 */
migrate((txApp) => {
  const collection = txApp.findCollectionByNameOrId("pbc_3146854971");

  collection.listRule = "1=1";
  collection.viewRule = "1=1";

  return txApp.save(collection);
}, (txApp) => {
  const collection = txApp.findCollectionByNameOrId("pbc_3146854971");

  collection.listRule = '@request.auth.id != ""';
  collection.viewRule = '@request.auth.id != ""';

  return txApp.save(collection);
});
