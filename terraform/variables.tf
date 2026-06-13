variable "aws_region" {
  description = "AWS region"
  default     = "ap-south-1"
}

variable "project_name" {
  description = "Project name used for resource naming"
  default     = "production-ops-platform"
}

variable "instance_type" {
  description = "EC2 instance type"
  default     = "t3.micro"
}

variable "ami_id" {
  description = "Amazon Linux 2 AMI for ap-south-1"
  default     = "ami-0e38835daf6b8a2b9"
}
