# A private network for gateway databases, shared by every gateway stack.
#
# Kong reaches Postgres only over TCP (its init phase can't use Cloud Run's
# /cloudsql Unix socket), and Google's documented TCP path from Cloud Run is a
# private IP over Direct VPC egress (ADR 0016). Nothing on this network accepts
# traffic from the internet:
# - Cloud SQL instances on it have a private IP only (ipv4_enabled = false).
# - There is no default route, so nothing on it reaches the internet either;
#   gateways use egress = PRIVATE_RANGES_ONLY, so their model calls leave Cloud
#   Run as before and only database traffic enters the VPC.
# - Ingress is denied except from Google's IAP TCP-forwarding range, for any
#   future admin VM (none exists).

resource "google_compute_network" "this" {
  name                            = "agw-vpc"
  auto_create_subnetworks         = false
  routing_mode                    = "REGIONAL"
  delete_default_routes_on_create = true

  depends_on = [time_sleep.api_propagation]
}

# Direct VPC egress takes Cloud Run instance IPs from here: a few per instance,
# and every gateway is capped at one instance.
resource "google_compute_subnetwork" "run" {
  name                     = "agw-run-${var.region}"
  network                  = google_compute_network.this.id
  region                   = var.region
  ip_cidr_range            = "10.10.0.0/24"
  private_ip_google_access = true
}

# Private services access: Cloud SQL private IPs come from this range, through
# one peering with Google's service network. A /20 holds far more instances than
# the lab will run. The peering can only be removed once every instance using it
# is gone (only matters if foundation/ itself is destroyed).
resource "google_compute_global_address" "private_services" {
  name          = "agw-private-services"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  address       = "10.20.0.0"
  prefix_length = 20
  network       = google_compute_network.this.id
}

resource "google_service_networking_connection" "private_services" {
  network                 = google_compute_network.this.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_services.name]
  # Deleting the peering fails while any Cloud SQL instance still uses it
  # ("Producer services still using this connection"); abandon it instead.
  deletion_policy = "ABANDON"
}

# Ingress is denied by default (implied rule, priority 65535); these make the
# intent explicit and log what the deny catches.
resource "google_compute_firewall" "allow_iap" {
  name          = "agw-allow-iap-ingress"
  network       = google_compute_network.this.id
  direction     = "INGRESS"
  priority      = 1000
  source_ranges = ["35.235.240.0/20"] # Google's IAP TCP forwarding

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }
}

resource "google_compute_firewall" "deny_ingress" {
  name          = "agw-deny-all-ingress"
  network       = google_compute_network.this.id
  direction     = "INGRESS"
  priority      = 65000
  source_ranges = ["0.0.0.0/0"]

  deny {
    protocol = "all"
  }

  log_config {
    metadata = "EXCLUDE_ALL_METADATA"
  }
}
