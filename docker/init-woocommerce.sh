#!/usr/bin/env bash
set -e

echo "==> Waiting for MariaDB database to be ready..."
until wp db check --allow-root > /dev/null 2>&1; do
    echo "Database unavailable. Retrying in 2 seconds..."
    sleep 2
done

echo "==> Database connected."

# Check if WordPress is already installed
if ! wp core is-installed --allow-root > /dev/null 2>&1; then
    echo "==> Installing WordPress core..."
    wp core install \
        --url="http://localhost:8080" \
        --title="Agent Studio Local Store" \
        --admin_user="admin" \
        --admin_password="admin_local_password_123!" \
        --admin_email="admin@example.com" \
        --skip-email \
        --allow-root
else
    echo "==> WordPress is already installed."
fi

# Check if WooCommerce is installed and activated
if ! wp plugin is-active woocommerce --allow-root > /dev/null 2>&1; then
    echo "==> Installing and activating WooCommerce plugin..."
    wp plugin install woocommerce --activate --allow-root
else
    echo "==> WooCommerce plugin is already active."
fi

# Configure pretty permalinks (mandatory for WooCommerce REST API /wp-json/wc/v3/)
echo "==> Configuring pretty permalinks (/wp-json/wc/v3/ support)..."
wp rewrite structure '/%postname%/' --hard --allow-root
wp rewrite flush --hard --allow-root

# Ensure stock management is turned on in WooCommerce settings
wp option update woocommerce_manage_stock yes --allow-root

# Create read-only REST API Key if one does not exist
echo "==> Checking WooCommerce REST API keys..."
wp eval --allow-root '
global $wpdb;
$table = $wpdb->prefix . "woocommerce_api_keys";
$existing = $wpdb->get_row("SELECT * FROM $table WHERE description = '\''Agent Studio Read-Only Key'\''");

if ($existing) {
    echo "Agent Studio Read-Only API Key already exists in database.\n";
    echo "Truncated Key: " . $existing->truncated_key . "\n";
} else {
    $user_id = 1;
    $description = "Agent Studio Read-Only Key";
    $permissions = "read";

    $consumer_key = "ck_" . bin2hex(random_bytes(20));
    $consumer_secret = "cs_" . bin2hex(random_bytes(20));

    $wpdb->insert(
        $table,
        array(
            "user_id" => $user_id,
            "description" => $description,
            "permissions" => $permissions,
            "consumer_key" => wc_api_hash($consumer_key),
            "consumer_secret" => $consumer_secret,
            "truncated_key" => substr($consumer_key, -7),
        ),
        array("%d", "%s", "%s", "%s", "%s", "%s")
    );

    echo "\n";
    echo "===============================================================\n";
    echo "  WOOCOMMERCE REST API CREDENTIALS GENERATED (READ-ONLY)       \n";
    echo "===============================================================\n";
    echo "Store URL:        http://localhost:8080\n";
    echo "Consumer Key:     " . $consumer_key . "\n";
    echo "Consumer Secret:  " . $consumer_secret . "\n";
    echo "Permissions:      " . $permissions . "\n";
    echo "===============================================================\n";
    echo "Add these to your local .env file (DO NOT commit to Git!)\n\n";
}
'

echo "==> WooCommerce Sandbox initialization complete!"
