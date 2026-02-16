/// <reference path="../pb_data/types.d.ts" />
/**
 * Add plausibility check fields to ingredients: plausibilityStatus (ok | suspicious | likely_wrong),
 * plausibilityResult (JSON: why, whatToVerify, confidence, suggestedCorrection). Idempotent.
 */
migrate((txApp) => {
  const collection = txApp.findCollectionByNameOrId("pbc_3146854971");

  if (!collection.fields.getByName("plausibilityStatus")) {
    collection.fields.add(new Field({
      "autogeneratePattern": "",
      "hidden": false,
      "id": "text_plaus_status",
      "max": 0,
      "min": 0,
      "name": "plausibilityStatus",
      "pattern": "",
      "presentable": false,
      "primaryKey": false,
      "required": false,
      "system": false,
      "type": "text"
    }));
  }

  if (!collection.fields.getByName("plausibilityResult")) {
    collection.fields.add(new Field({
      "hidden": false,
      "id": "json_plaus_result",
      "maxSize": 0,
      "name": "plausibilityResult",
      "presentable": false,
      "required": false,
      "system": false,
      "type": "json"
    }));
  }

  return txApp.save(collection);
}, (txApp) => {
  const collection = txApp.findCollectionByNameOrId("pbc_3146854971");
  try {
    collection.fields.removeById("text_plaus_status");
  } catch (e) {}
  try {
    collection.fields.removeById("json_plaus_result");
  } catch (e) {}
  return txApp.save(collection);
});
