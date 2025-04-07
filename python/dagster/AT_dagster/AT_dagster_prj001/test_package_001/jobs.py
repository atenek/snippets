from dagster import define_asset_job, AssetSelection


my_sync_job = define_asset_job(
    name="sync_company_data",
    selection=AssetSelection.assets('store_to_db')
)