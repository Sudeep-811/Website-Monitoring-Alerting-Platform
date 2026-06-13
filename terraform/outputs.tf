output "jenkins_public_ip" {
  description = "Jenkins server public IP"
  value       = aws_instance.jenkins.public_ip
}

output "monitoring_public_ip" {
  description = "Monitoring server public IP"
  value       = aws_instance.monitoring.public_ip
}

output "jenkins_url" {
  description = "Jenkins dashboard URL"
  value       = "http://${aws_instance.jenkins.public_ip}:8080"
}

output "grafana_url" {
  description = "Grafana dashboard URL"
  value       = "http://${aws_instance.monitoring.public_ip}:3000"
}

output "prometheus_url" {
  description = "Prometheus URL"
  value       = "http://${aws_instance.monitoring.public_ip}:9090"
}

output "alertmanager_url" {
  description = "Alertmanager URL"
  value       = "http://${aws_instance.monitoring.public_ip}:9093"
}
