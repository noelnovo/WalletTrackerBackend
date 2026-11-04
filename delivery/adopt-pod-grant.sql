-- Run only on a private restored MariaDB11.4.12 instance, in the SAME import
-- connection before its final FLUSH PRIVILEGES. No password literal or rotation.
-- The observed k3s node pod CIDR is10.42.0.0/24; fail closed if source drifted.
DELIMITER //
BEGIN NOT ATOMIC
  IF (SELECT COUNT(*) FROM mysql.global_priv WHERE User='root' AND Host='10.2.0.201') != 1 THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Expected source account absent; operator review required';
  END IF;
  IF (SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA='wallet_tracker' AND TABLE_NAME='User') != 1 THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Restored main schema absent';
  END IF;
  INSERT INTO mysql.global_priv (Host, User, Priv)
    SELECT '10.42.0.%', User, Priv FROM mysql.global_priv
    WHERE User='root' AND Host='10.2.0.201'
    ON DUPLICATE KEY UPDATE Priv=VALUES(Priv);
END//
DELIMITER ;
FLUSH PRIVILEGES;
-- Operator must compare protected source/target row, account and key proofs
-- before issuing the separate checkpoint statement in the migration plan.
