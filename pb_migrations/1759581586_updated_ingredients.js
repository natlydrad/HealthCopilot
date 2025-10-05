/// <reference path="../pb_data/types.d.ts" />
migrate((app) => {
  const collection = app.findCollectionByNameOrId("pbc_3146854971")

  // add field
  collection.fields.addAt(0, new Field({
    "cascadeDelete": false,
    "collectionId": "pbc_695162881",
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

  return app.save(collection)
}, (app) => {
  const collection = app.findCollectionByNameOrId("pbc_3146854971")

  // remove field
  collection.fields.removeById("relation4249466421")

  return app.save(collection)
})
