import tensorflow as tf


@tf.keras.utils.register_keras_serializable(package="phase3_vae")
class ClipLogVar(tf.keras.layers.Layer):
    # Replaces a Lambda layer: Lambda.from_config() rebuilds its closure using
    # keras's own python_utils module globals (no `tf` there), so the loaded
    # layer raised NameError on call in a fresh process. A real Layer subclass
    # has no closure to lose and deserializes with plain safe_mode=True.
    # (tf.keras.utils.register_keras_serializable, not tf.keras.saving - the
    # latter isn't exposed on this tf/keras version's lazy-loaded tf.keras
    # namespace, though both point at the same underlying keras function.)
    def call(self, inputs):
        return tf.clip_by_value(inputs, -10.0, 10.0)

    def compute_output_shape(self, input_shape):
        return input_shape


@tf.keras.utils.register_keras_serializable(package="phase3_vae")
class VAE2(tf.keras.Model):
    """Same architecture as VAE, but beta is a tf.Variable so a callback can
    anneal it mid-training (VAE's beta was a plain float, fixed for the whole run)."""
    def __init__(self, input_dim, latent_dim, beta_init=1.0, dropout_rate=0.1, **kwargs):
        super().__init__(**kwargs)
        self.input_dim = input_dim
        self.latent_dim = latent_dim
        self.dropout_rate = dropout_rate
        self.beta = tf.Variable(beta_init, trainable=False, dtype=tf.float32, name="beta")

        enc_in = tf.keras.Input(shape=(input_dim,))
        x = tf.keras.layers.Dense(16, activation="relu")(enc_in)
        x = tf.keras.layers.Dropout(dropout_rate)(x)
        x = tf.keras.layers.Dense(8, activation="relu")(x)
        z_mean = tf.keras.layers.Dense(latent_dim, name="z_mean")(x)
        z_log_var_raw = tf.keras.layers.Dense(latent_dim, name="z_log_var")(x)
        z_log_var = ClipLogVar()(z_log_var_raw)
        self.encoder = tf.keras.Model(enc_in, [z_mean, z_log_var], name="encoder")

        dec_in = tf.keras.Input(shape=(latent_dim,))
        y = tf.keras.layers.Dense(8, activation="relu")(dec_in)
        y = tf.keras.layers.Dense(16, activation="relu")(y)
        dec_out = tf.keras.layers.Dense(input_dim, activation="linear")(y)
        self.decoder = tf.keras.Model(dec_in, dec_out, name="decoder")

        self.total_loss_tracker = tf.keras.metrics.Mean(name="loss")
        self.recon_loss_tracker = tf.keras.metrics.Mean(name="recon_loss")
        self.kl_loss_tracker = tf.keras.metrics.Mean(name="kl_loss")

    @property
    def metrics(self):
        return [self.total_loss_tracker, self.recon_loss_tracker, self.kl_loss_tracker]

    def call(self, inputs, training=False):
        z_mean, z_log_var = self.encoder(inputs, training=training)
        eps = tf.random.normal(shape=tf.shape(z_mean))
        z = z_mean + tf.exp(0.5 * z_log_var) * eps
        recon = self.decoder(z, training=training)
        return recon, z_mean, z_log_var

    def _compute_losses(self, x, y):
        recon, z_mean, z_log_var = self(x, training=True)
        recon_loss = tf.reduce_mean(tf.reduce_sum(tf.square(y - recon), axis=1))
        kl_loss = -0.5 * tf.reduce_mean(
            tf.reduce_sum(1 + z_log_var - tf.square(z_mean) - tf.exp(z_log_var), axis=1)
        )
        total_loss = recon_loss + self.beta * kl_loss
        return total_loss, recon_loss, kl_loss

    def train_step(self, data):
        x, y = data
        with tf.GradientTape() as tape:
            total_loss, recon_loss, kl_loss = self._compute_losses(x, y)
        grads = tape.gradient(total_loss, self.trainable_weights)
        self.optimizer.apply_gradients(zip(grads, self.trainable_weights))
        self.total_loss_tracker.update_state(total_loss)
        self.recon_loss_tracker.update_state(recon_loss)
        self.kl_loss_tracker.update_state(kl_loss)
        return {m.name: m.result() for m in self.metrics}

    def test_step(self, data):
        x, y = data
        total_loss, recon_loss, kl_loss = self._compute_losses(x, y)
        self.total_loss_tracker.update_state(total_loss)
        self.recon_loss_tracker.update_state(recon_loss)
        self.kl_loss_tracker.update_state(kl_loss)
        return {m.name: m.result() for m in self.metrics}

    def get_config(self):
        config = super().get_config()
        config.update({
            "input_dim": self.input_dim,
            "latent_dim": self.latent_dim,
            "beta_init": float(self.beta.numpy()),
            "dropout_rate": self.dropout_rate,
        })
        return config

    @classmethod
    def from_config(cls, config):
        config = dict(config)
        return cls(
            input_dim=config.pop("input_dim"),
            latent_dim=config.pop("latent_dim"),
            beta_init=config.pop("beta_init"),
            dropout_rate=config.pop("dropout_rate"),
            name=config.get("name"),
        )
