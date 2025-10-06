/// <reference path="../pb_data/types.d.ts" />
migrate((app) => {
  const collection = app.findCollectionByNameOrId("pbc_1698011294")

  // add field
  collection.fields.addAt(8, new Field({
    "hidden": false,
    "id": "date1431492372",
    "max": "",
    "min": "",
    "name": "parsed_at",
    "presentable": false,
    "required": false,
    "system": false,
    "type": "date"
  }))

  // add field
  collection.fields.addAt(9, new Field({
    "hidden": false,
    "id": "json852869811",
    "maxSize": 0,
    "name": "routes",
    "presentable": false,
    "required": false,
    "system": false,
    "type": "json"
  }))

  return app.save(collection)
}, (app) => {
  const collection = app.findCollectionByNameOrId("pbc_1698011294")

  // remove field
  collection.fields.removeById("date1431492372")

  // remove field
  collection.fields.removeById("json852869811")

  return app.save(collection)
})
