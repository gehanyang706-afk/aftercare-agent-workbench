
CREATE TABLE customers (
	id VARCHAR NOT NULL,
	name VARCHAR NOT NULL,
	PRIMARY KEY (id)
)

;

CREATE TABLE policies (
	id VARCHAR NOT NULL,
	rules JSON NOT NULL,
	content_hash VARCHAR NOT NULL,
	current BOOLEAN NOT NULL,
	PRIMARY KEY (id)
)

;
CREATE UNIQUE INDEX one_current_policy ON policies (current) WHERE "current" = true;

CREATE TABLE variants (
	id VARCHAR NOT NULL,
	product_id VARCHAR NOT NULL,
	title VARCHAR NOT NULL,
	color VARCHAR NOT NULL,
	size VARCHAR NOT NULL,
	price_fen INTEGER NOT NULL,
	returnable BOOLEAN NOT NULL,
	exchangeable BOOLEAN NOT NULL,
	category VARCHAR NOT NULL,
	PRIMARY KEY (id),
	CHECK (price_fen >= 0)
)

;

CREATE TABLE conversations (
	id VARCHAR NOT NULL,
	customer_id VARCHAR NOT NULL,
	revision INTEGER NOT NULL,
	status VARCHAR NOT NULL,
	"case" JSON NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(customer_id) REFERENCES customers (id)
)

;
CREATE INDEX ix_conversations_customer_id ON conversations (customer_id);

CREATE TABLE inventory (
	variant_id VARCHAR NOT NULL,
	available INTEGER NOT NULL,
	reserved INTEGER NOT NULL,
	version INTEGER NOT NULL,
	PRIMARY KEY (variant_id),
	CHECK (available >= 0 AND reserved >= 0),
	FOREIGN KEY(variant_id) REFERENCES variants (id)
)

;

CREATE TABLE orders (
	id VARCHAR NOT NULL,
	customer_id VARCHAR NOT NULL,
	status VARCHAR NOT NULL,
	paid_fen INTEGER NOT NULL,
	delivered_at TIMESTAMP WITH TIME ZONE,
	version INTEGER NOT NULL,
	policy_version VARCHAR NOT NULL,
	PRIMARY KEY (id),
	CHECK (paid_fen >= 0),
	FOREIGN KEY(customer_id) REFERENCES customers (id),
	FOREIGN KEY(policy_version) REFERENCES policies (id)
)

;
CREATE INDEX ix_orders_customer_id ON orders (customer_id);

CREATE TABLE action_previews (
	id VARCHAR NOT NULL,
	conversation_id VARCHAR NOT NULL,
	customer_id VARCHAR NOT NULL,
	order_id VARCHAR NOT NULL,
	payload JSON NOT NULL,
	parameter_hash VARCHAR NOT NULL,
	revision INTEGER NOT NULL,
	order_version INTEGER NOT NULL,
	eligibility_policy VARCHAR NOT NULL,
	flow_policy VARCHAR NOT NULL,
	policy_hash VARCHAR NOT NULL,
	status VARCHAR NOT NULL,
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(conversation_id) REFERENCES conversations (id),
	FOREIGN KEY(customer_id) REFERENCES customers (id),
	FOREIGN KEY(order_id) REFERENCES orders (id)
)

;
CREATE INDEX ix_action_previews_conversation_id ON action_previews (conversation_id);
CREATE UNIQUE INDEX unique_active_preview ON action_previews (conversation_id, revision, parameter_hash) WHERE status IN ('PENDING', 'CONFIRMED');

CREATE TABLE events (
	id BIGSERIAL NOT NULL,
	conversation_id VARCHAR NOT NULL,
	event_type VARCHAR NOT NULL,
	payload JSON NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(conversation_id) REFERENCES conversations (id)
)

;
CREATE INDEX ix_events_conversation_id ON events (conversation_id);

CREATE TABLE handoff_tickets (
	id VARCHAR NOT NULL,
	conversation_id VARCHAR NOT NULL,
	revision INTEGER NOT NULL,
	reason_code VARCHAR NOT NULL,
	summary TEXT NOT NULL,
	status VARCHAR NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (conversation_id, revision, reason_code),
	FOREIGN KEY(conversation_id) REFERENCES conversations (id)
)

;

CREATE TABLE messages (
	id VARCHAR NOT NULL,
	conversation_id VARCHAR NOT NULL,
	client_message_id VARCHAR NOT NULL,
	role VARCHAR NOT NULL,
	text TEXT NOT NULL,
	revision INTEGER NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (conversation_id, client_message_id),
	FOREIGN KEY(conversation_id) REFERENCES conversations (id)
)

;
CREATE INDEX ix_messages_conversation_id ON messages (conversation_id);

CREATE TABLE order_lines (
	id VARCHAR NOT NULL,
	order_id VARCHAR NOT NULL,
	variant_id VARCHAR NOT NULL,
	quantity INTEGER NOT NULL,
	occupied INTEGER NOT NULL,
	unused BOOLEAN NOT NULL,
	PRIMARY KEY (id),
	CHECK (quantity > 0 AND occupied >= 0 AND occupied <= quantity),
	FOREIGN KEY(order_id) REFERENCES orders (id),
	FOREIGN KEY(variant_id) REFERENCES variants (id)
)

;
CREATE INDEX ix_order_lines_order_id ON order_lines (order_id);

CREATE TABLE approvals (
	preview_id VARCHAR NOT NULL,
	customer_id VARCHAR NOT NULL,
	parameter_hash VARCHAR NOT NULL,
	revision INTEGER NOT NULL,
	confirmed_at TIMESTAMP WITH TIME ZONE NOT NULL,
	method VARCHAR NOT NULL,
	PRIMARY KEY (preview_id),
	FOREIGN KEY(preview_id) REFERENCES action_previews (id),
	FOREIGN KEY(customer_id) REFERENCES customers (id)
)

;

CREATE TABLE operations (
	id VARCHAR NOT NULL,
	preview_id VARCHAR NOT NULL,
	customer_id VARCHAR NOT NULL,
	idempotency_key VARCHAR NOT NULL,
	request_hash VARCHAR NOT NULL,
	status VARCHAR NOT NULL,
	receipt JSON NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (customer_id, idempotency_key),
	UNIQUE (preview_id),
	FOREIGN KEY(preview_id) REFERENCES action_previews (id),
	FOREIGN KEY(customer_id) REFERENCES customers (id)
)

;

CREATE TABLE aftercare_requests (
	id VARCHAR NOT NULL,
	operation_id VARCHAR NOT NULL,
	line_id VARCHAR NOT NULL,
	action VARCHAR NOT NULL,
	quantity INTEGER NOT NULL,
	target_variant VARCHAR,
	status VARCHAR NOT NULL,
	PRIMARY KEY (id),
	CHECK (quantity > 0),
	UNIQUE (operation_id),
	FOREIGN KEY(operation_id) REFERENCES operations (id),
	FOREIGN KEY(line_id) REFERENCES order_lines (id),
	FOREIGN KEY(target_variant) REFERENCES variants (id)
)

;
CREATE INDEX ix_aftercare_requests_line_id ON aftercare_requests (line_id);

CREATE TABLE idempotency_bindings (
	customer_id VARCHAR NOT NULL,
	key VARCHAR NOT NULL,
	request_hash VARCHAR NOT NULL,
	operation_id VARCHAR NOT NULL,
	PRIMARY KEY (customer_id, key),
	FOREIGN KEY(customer_id) REFERENCES customers (id),
	FOREIGN KEY(operation_id) REFERENCES operations (id)
)

;

CREATE TABLE refund_requests (
	id VARCHAR NOT NULL,
	operation_id VARCHAR NOT NULL,
	amount_fen INTEGER NOT NULL,
	status VARCHAR NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (operation_id),
	FOREIGN KEY(operation_id) REFERENCES operations (id)
)

;

CREATE TABLE inventory_reservations (
	application_id VARCHAR NOT NULL,
	variant_id VARCHAR NOT NULL,
	quantity INTEGER NOT NULL,
	status VARCHAR NOT NULL,
	PRIMARY KEY (application_id),
	CHECK (quantity > 0),
	FOREIGN KEY(application_id) REFERENCES aftercare_requests (id),
	FOREIGN KEY(variant_id) REFERENCES inventory (variant_id)
)

;
