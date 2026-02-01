/// <reference path="../pb_data/types.d.ts" />
migrate((txApp) => {
  const collection = txApp.findCollectionByNameOrId("pbc_3146854971")

  // Add mealId relation field - links ingredient to meal
  // Skip if field already exists (idempotent)
  if (!collection.fields.getById("relation4249466421")) {
    const existingFields = collection.fields.getAll();
    collection.fields.addAt(0, new Field({
      "cascadeDelete": false,
      "collectionId": "pbc_695162881", // meals collection ID
      "hidden": false,
      "id": "relation4249466421",
      "maxSelect": 1,
      "minSelect": 0,
      "name": "mealId",
      "presentable": false,
      "required": false,
      "system": false,
      "type": "relation"
    }))
  }

  return txApp.save(collection)
}, (txApp) => {
  const collection = txApp.findCollectionByNameOrId("pbc_3146854971")

  // Rollback: remove mealId field
  collection.fields.removeById("relation4249466421")

  return txApp.save(collection)
})
