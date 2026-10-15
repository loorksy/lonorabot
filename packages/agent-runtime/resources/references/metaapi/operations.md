# MetaApi adapter reference
MetaApi is an adapter, not Agent identity or financial authority. Use saved Lonora connection_id, not provisioning UUID as broker login. The broker-native login/server/name come from verified account data. Connection lifecycle, history region selection and reconnection are implemented by the adapter. Never inject credentials into context.
