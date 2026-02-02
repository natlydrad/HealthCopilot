/// <reference path="../pb_data/types.d.ts" />
migrate((txApp) => {
  const collection = txApp.findCollectionByNameOrId("pbc_3146854971")

  // Check if field already exists
  if (!collection.fields.getByName("mealId")) {
    collection.fields.add(new Field({
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

  // Rollback: remove mealId field (only if it exists)
  try {
    collection.fields.removeById("relation4249466421")
  } catch (e) {
    // Field doesn't exist, skip
  }

  return txApp.save(collection)
})
