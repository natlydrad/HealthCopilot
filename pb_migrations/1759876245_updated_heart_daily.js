/// <reference path="../pb_data/types.d.ts" />
migrate((app) => {
  const collection = app.findCollectionByNameOrId("pbc_1317157814")

  // remove field
  collection.fields.removeById("autodate2862495610")

  // add field
  collection.fields.addAt(5, new Field({
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

  return app.save(collection)
}, (app) => {
  const collection = app.findCollectionByNameOrId("pbc_1317157814")

  // add field
  collection.fields.addAt(7, new Field({
    "hidden": false,
    "id": "autodate2862495610",
    "name": "date",
    "onCreate": true,
    "onUpdate": false,
    "presentable": false,
    "system": false,
    "type": "autodate"
  }))

  // remove field
  collection.fields.removeById("date2862495610")

  return app.save(collection)
})
