/// <reference path="../pb_data/types.d.ts" />
migrate((app) => {
  const collection = app.findCollectionByNameOrId("pbc_3768393438")

  // update collection data
  unmarshal({
    "createRule": "1=1",
    "deleteRule": "1=1",
    "listRule": "  1=1",
    "updateRule": "1=1",
    "viewRule": "1=1"
  }, collection)

  return app.save(collection)
}, (app) => {
  const collection = app.findCollectionByNameOrId("pbc_3768393438")

  // update collection data
  unmarshal({
    "createRule": null,
    "deleteRule": null,
    "listRule": null,
    "updateRule": null,
    "viewRule": null
  }, collection)

  return app.save(collection)
})
