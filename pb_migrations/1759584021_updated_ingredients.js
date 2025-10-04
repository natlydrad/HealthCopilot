/// <reference path="../pb_data/types.d.ts" />
migrate((app) => {
  const collection = app.findCollectionByNameOrId("pbc_3146854971")

  // add field
  collection.fields.addAt(9, new Field({
    "hidden": false,
    "id": "json1764125218",
    "maxSize": 0,
    "name": "rawUSDA",
    "presentable": false,
    "required": false,
    "system": false,
    "type": "json"
  }))

  // update field
  collection.fields.addAt(8, new Field({
    "hidden": false,
    "id": "json3305188680",
    "maxSize": 0,
    "name": "rawGPT",
    "presentable": false,
    "required": false,
    "system": false,
    "type": "json"
  }))

  return app.save(collection)
}, (app) => {
  const collection = app.findCollectionByNameOrId("pbc_3146854971")

  // remove field
  collection.fields.removeById("json1764125218")

  // update field
  collection.fields.addAt(8, new Field({
    "hidden": false,
    "id": "json3305188680",
    "maxSize": 0,
    "name": "rawResponse",
    "presentable": false,
    "required": false,
    "system": false,
    "type": "json"
  }))

  return app.save(collection)
})
