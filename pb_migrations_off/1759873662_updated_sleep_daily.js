/// <reference path="../pb_data/types.d.ts" />
migrate((app) => {
  const collection = app.findCollectionByNameOrId("pbc_3768393438")

  // remove field
  collection.fields.removeById("date2862495610")

  // add field
  collection.fields.addAt(1, new Field({
    "hidden": false,
    "id": "autodate2862495610",
    "name": "date",
    "onCreate": true,
    "onUpdate": false,
    "presentable": false,
    "system": false,
    "type": "autodate"
  }))

  return app.save(collection)
}, (app) => {
  const collection = app.findCollectionByNameOrId("pbc_3768393438")

  // add field
  collection.fields.addAt(1, new Field({
    "hidden": false,
    "id": "date2862495610",
    "max": "",
    "min": "",
    "name": "date",
    "presentable": false,
    "required": false,
    "system": false,
    "type": "date"
  }))

  // remove field
  collection.fields.removeById("autodate2862495610")

  return app.save(collection)
})
